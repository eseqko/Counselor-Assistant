"""Data Visualizations — analytics dashboard with Chart.js."""
from datetime import date, timedelta
from collections import Counter, defaultdict
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.student import Student
from app.models.grade import GradeRecord
from app.models.attendance import AttendanceRecord
from app.models.note import Note
from app.models.service_record import ServiceRecord
from app.models.activity import Activity
from app.models.elpac import ELPACScore
from app.utils.elpi import (
    compute_elpi, elpi_rank, SIMPLIFIED_CATEGORIES, FULL_CATEGORIES,
)

analytics_bp = Blueprint('analytics', __name__)


@analytics_bp.route('/')
@login_required
def index():
    return render_template('analytics/index.html')


@analytics_bp.route('/api/data')
@login_required
def api_data():
    """Return all chart data in a single payload."""
    uid = current_user.id
    today = date.today()

    # Time range from query params (default: current school year)
    range_key = request.args.get('range', 'year')
    if range_key == '30':
        start = today - timedelta(days=30)
    elif range_key == '90':
        start = today - timedelta(days=90)
    elif range_key == 'semester':
        start = date(today.year, 1, 1) if today.month >= 1 else date(today.year - 1, 8, 1)
    else:  # year
        start = date(today.year - 1, 8, 1) if today.month < 8 else date(today.year, 8, 1)

    students = Student.query.filter_by(
        assigned_counselor_id=uid, status='active').all()
    student_ids = [s.id for s in students]

    data = {
        'caseload': _caseload_data(students),
        'academic': _academic_data(student_ids) if student_ids else {},
        'attendance': _attendance_data(student_ids, start, today) if student_ids else {},
        'services': _services_data(uid, start, today),
        'activities': _activities_data(uid, start, today),
        'contacts': _contacts_over_time(uid, start, today),
        'followups': _followup_data(uid),
        'range': {'start': start.isoformat(), 'end': today.isoformat()},
    }

    return jsonify(data)


# ── Insights 360: academic-risk + attendance pattern drill-down ───

# Grade buckets used across the insights aggregations.
_FAILING = {'F', 'NP'}
_NEAR_FAILING = {'D+', 'D', 'D-'}
_DF = _FAILING | _NEAR_FAILING


@analytics_bp.route('/insights')
@login_required
def insights():
    """360 drill-down: which classes give the most D/F, which periods students
    miss the most, grade distribution, and the academic+attendance overlap."""
    return render_template('analytics/insights.html')


@analytics_bp.route('/api/insights')
@login_required
def api_insights():
    """Single-payload data for the Insights 360 page."""
    uid = current_user.id
    today = date.today()

    students = Student.query.filter_by(
        assigned_counselor_id=uid, status='active').all()
    student_ids = [s.id for s in students]
    name_by_id = {s.id: s for s in students}

    if not student_ids:
        return jsonify({'empty': True})

    # School-year filter. Default to the most recent year present in grades.
    years = sorted({y[0] for y in db.session.query(GradeRecord.school_year)
                    .filter(GradeRecord.student_id.in_(student_ids),
                            GradeRecord.school_year.isnot(None)).distinct().all()},
                   reverse=True)
    year = request.args.get('year') or (years[0] if years else None)
    final_only = request.args.get('final_only', '1') != '0'

    grades_payload = _insights_grades(student_ids, year, final_only)
    attend_payload = _insights_attendance(student_ids, today - timedelta(days=365), today)
    overlap = _insights_overlap(grades_payload['_per_student_df'],
                                attend_payload['_per_student_absent'], name_by_id)

    # Headline summary cards
    course_rows = grades_payload['df_by_course']['rows']
    worst_course = course_rows[0] if course_rows else None
    ap = attend_payload['attend_by_period']
    worst_period = None
    if ap['labels']:
        idx = max(range(len(ap['labels'])), key=lambda i: ap['absent'][i])
        if ap['absent'][idx] > 0:
            worst_period = {'label': ap['labels'][idx], 'count': ap['absent'][idx]}

    summary = {
        'total_df': grades_payload['total_df'],
        'courses_with_df': len(course_rows),
        'worst_course': worst_course['course'] if worst_course else '--',
        'worst_course_df': worst_course['df'] if worst_course else 0,
        'failing_students': grades_payload['failing_students'],
        'total_absences': attend_payload['total_absences'],
        'worst_period': worst_period,
        'at_risk_overlap': len(overlap),
    }

    # Drop internal scratch keys before serializing.
    grades_payload.pop('_per_student_df', None)
    attend_payload.pop('_per_student_absent', None)

    return jsonify({
        'filters': {'year': year, 'years': years, 'final_only': final_only},
        'summary': summary,
        'grades': grades_payload,
        'attendance': attend_payload,
        'high_risk': overlap,
    })


def _insights_grades(student_ids, year, final_only):
    """Academic-risk aggregations: D/F by course, by period, by subject, and the
    overall grade distribution."""
    q = GradeRecord.query.filter(GradeRecord.student_id.in_(student_ids))
    if final_only:
        q = q.filter(GradeRecord.grade_type == 'final')
    if year:
        q = q.filter(GradeRecord.school_year == year)
    grades = q.all()

    by_course = defaultdict(lambda: {'f': 0, 'd': 0, 'total': 0, 'students': set()})
    by_teacher = defaultdict(lambda: {'f': 0, 'd': 0, 'total': 0, 'students': set()})
    by_period = defaultdict(lambda: {'df': 0, 'total': 0})
    by_subject = defaultdict(lambda: {'f': 0, 'd': 0})
    dist = Counter()
    per_student_df = defaultdict(int)
    total_df = 0
    failing_students = set()

    for g in grades:
        lg = (g.letter_grade or '').strip()
        # Overall grade distribution bucket
        if lg in ('A+', 'A', 'A-'): dist['A'] += 1
        elif lg in ('B+', 'B', 'B-'): dist['B'] += 1
        elif lg in ('C+', 'C', 'C-'): dist['C'] += 1
        elif lg in _NEAR_FAILING: dist['D'] += 1
        elif lg == 'F': dist['F'] += 1
        elif lg in ('P', 'NP'): dist['P/NP'] += 1
        elif lg: dist['Other'] += 1

        course = (g.course_name or 'Unknown').strip()
        teacher = (g.teacher or '').strip()
        by_course[course]['total'] += 1
        if teacher:
            by_teacher[teacher]['total'] += 1
        if g.period is not None:
            by_period[g.period]['total'] += 1

        is_df = lg in _DF
        if is_df:
            total_df += 1
            per_student_df[g.student_id] += 1
            failing_students.add(g.student_id)
            by_course[course]['students'].add(g.student_id)
            if g.period is not None:
                by_period[g.period]['df'] += 1
            subj = g.subject_area or course or 'Unknown'
            is_f = lg in ('F', 'NP')
            if is_f:
                by_course[course]['f'] += 1
                by_subject[subj]['f'] += 1
            else:
                by_course[course]['d'] += 1
                by_subject[subj]['d'] += 1
            if teacher:
                by_teacher[teacher]['students'].add(g.student_id)
                by_teacher[teacher]['f' if is_f else 'd'] += 1

    # D/F by course — rank by total D/F, then by rate
    course_rows = []
    for name, c in by_course.items():
        df = c['f'] + c['d']
        if df == 0:
            continue
        course_rows.append({
            'course': name, 'df': df, 'f': c['f'], 'd': c['d'],
            'students': len(c['students']), 'total': c['total'],
            'rate': round(df / c['total'] * 100, 1) if c['total'] else 0,
        })
    course_rows.sort(key=lambda r: (-r['df'], -r['rate']))
    top_courses = course_rows[:15]

    # D/F by teacher — same shape as by course
    teacher_rows = []
    for name, c in by_teacher.items():
        df = c['f'] + c['d']
        if df == 0:
            continue
        teacher_rows.append({
            'teacher': name, 'df': df, 'f': c['f'], 'd': c['d'],
            'students': len(c['students']), 'total': c['total'],
            'rate': round(df / c['total'] * 100, 1) if c['total'] else 0,
        })
    teacher_rows.sort(key=lambda r: (-r['df'], -r['rate']))
    top_teachers = teacher_rows[:15]

    # D/F by period (sorted by period number)
    periods = sorted(by_period.keys())
    period_payload = {
        'labels': [f'Period {p}' for p in periods],
        'df': [by_period[p]['df'] for p in periods],
        'total': [by_period[p]['total'] for p in periods],
        'rate': [round(by_period[p]['df'] / by_period[p]['total'] * 100, 1)
                 if by_period[p]['total'] else 0 for p in periods],
    }

    # D/F by subject (sorted by total)
    subj_sorted = sorted(by_subject.items(),
                         key=lambda kv: -(kv[1]['f'] + kv[1]['d']))
    subj_payload = {
        'labels': [s for s, _ in subj_sorted],
        'f_values': [v['f'] for _, v in subj_sorted],
        'd_values': [v['d'] for _, v in subj_sorted],
    }

    dist_order = ['A', 'B', 'C', 'D', 'F', 'P/NP', 'Other']
    return {
        'df_by_course': {
            'labels': [r['course'] for r in top_courses],
            'f_values': [r['f'] for r in top_courses],
            'd_values': [r['d'] for r in top_courses],
            'rows': course_rows,
        },
        'df_by_period': period_payload,
        'df_by_subject': subj_payload,
        'df_by_teacher': {
            'labels': [r['teacher'] for r in top_teachers],
            'f_values': [r['f'] for r in top_teachers],
            'd_values': [r['d'] for r in top_teachers],
            'rows': teacher_rows,
            'has_data': bool(by_teacher),
        },
        'grade_distribution': {
            'labels': dist_order,
            'values': [dist.get(k, 0) for k in dist_order],
        },
        'total_df': total_df,
        'failing_students': len(failing_students),
        '_per_student_df': per_student_df,
    }


_WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']


def _insights_attendance(student_ids, start, end):
    """Attendance patterns: absences/tardies by period, by weekday, by status,
    and the courses students miss most."""
    records = AttendanceRecord.query.filter(
        AttendanceRecord.student_id.in_(student_ids),
        AttendanceRecord.date >= start,
        AttendanceRecord.date <= end,
    ).all()

    by_period = defaultdict(lambda: {'absent': 0, 'tardy': 0})
    by_weekday = defaultdict(lambda: {'absent': 0, 'tardy': 0})
    by_status = Counter()
    by_course = defaultdict(int)
    per_student_absent = defaultdict(int)
    total_absences = 0

    for r in records:
        status = (r.status or '').lower()
        by_status[status] += 1
        if status == 'absent':
            total_absences += 1
            per_student_absent[r.student_id] += 1
        # Period-level breakdown (daily rows have period NULL — skip those here)
        if r.period is not None and r.period >= 1:
            if status == 'absent':
                by_period[r.period]['absent'] += 1
            elif status == 'tardy':
                by_period[r.period]['tardy'] += 1
        # Weekday pattern (any record with a date)
        if r.date and status in ('absent', 'tardy'):
            by_weekday[r.date.weekday()][status] += 1
        # Course the student is missing
        if status in ('absent', 'tardy') and r.course_name:
            by_course[r.course_name.strip()] += 1

    periods = sorted(by_period.keys())
    weekday_idx = list(range(5))  # Mon-Fri
    course_sorted = sorted(by_course.items(), key=lambda kv: -kv[1])[:12]
    status_order = ['present', 'absent', 'tardy', 'excused']

    return {
        'attend_by_period': {
            'labels': [f'Period {p}' for p in periods],
            'absent': [by_period[p]['absent'] for p in periods],
            'tardy': [by_period[p]['tardy'] for p in periods],
        },
        'attend_by_weekday': {
            'labels': [_WEEKDAYS[i] for i in weekday_idx],
            'absent': [by_weekday[i]['absent'] for i in weekday_idx],
            'tardy': [by_weekday[i]['tardy'] for i in weekday_idx],
        },
        'attend_by_status': {
            'labels': [s.title() for s in status_order if by_status.get(s)],
            'values': [by_status[s] for s in status_order if by_status.get(s)],
        },
        'attend_by_course': {
            'labels': [c for c, _ in course_sorted],
            'values': [n for _, n in course_sorted],
        },
        'has_period_data': bool(periods),
        'total_absences': total_absences,
        '_per_student_absent': per_student_absent,
    }


def _insights_overlap(per_student_df, per_student_absent, name_by_id):
    """Highest-risk students: 2+ D/F grades AND 5+ absences — the overlap where
    academic and attendance risk compound."""
    rows = []
    for sid in set(per_student_df) | set(per_student_absent):
        df = per_student_df.get(sid, 0)
        absent = per_student_absent.get(sid, 0)
        if df >= 2 and absent >= 5:
            s = name_by_id.get(sid)
            if not s:
                continue
            rows.append({
                'id': sid,
                'name': f'{s.first_name} {s.last_name}',
                'grade': s.grade_level,
                'df_count': df,
                'absences': absent,
            })
    rows.sort(key=lambda r: (-(r['df_count'] + r['absences'])))
    return rows


# ── ELPAC Analytics Dashboard ─────────────────────────────────────


YEARS_BUCKETS = [
    ('0_1', '0-1 years', 0, 1),
    ('1_3', '1-3 years', 1, 3),
    ('3_5', '3-5 years', 3, 5),
    ('5_plus', '5+ years', 5, 999),
]


def _years_in_us_schools_bucket(student):
    yrs = student.years_in_us_schools
    if yrs is None:
        return 'unknown'
    for key, _label, lo, hi in YEARS_BUCKETS:
        if lo <= yrs < hi:
            return key
    return '5_plus'


def _filter_students(students, grade, cohort, el_status, years_bucket):
    out = []
    for s in students:
        if grade != 'all' and (s.grade_level or 0) != int(grade):
            continue
        if cohort != 'all' and s.graduation_year != int(cohort):
            continue
        if el_status != 'all' and s.el_status != el_status:
            continue
        if years_bucket != 'all' and _years_in_us_schools_bucket(s) != years_bucket:
            continue
        out.append(s)
    return out


@analytics_bp.route('/elpac')
@login_required
def elpac_dashboard():
    """Caseload-wide ELPAC analytics with Chart.js views."""
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active').all()

    grade = request.args.get('grade_level', 'all')
    cohort = request.args.get('cohort', 'all')
    el_status = request.args.get('el_status', 'all')
    years_bucket = request.args.get('years_in_us_schools', 'all')

    filtered = _filter_students(students, grade, cohort, el_status, years_bucket)
    student_ids = [s.id for s in filtered]

    # Chart 1: Overall Level Distribution (latest test per student)
    overall_dist = Counter()
    latest_by_student = {}
    for s in filtered:
        latest = s.latest_elpac
        if latest:
            latest_by_student[s.id] = latest
            if latest.overall_level:
                overall_dist[latest.overall_level] += 1

    # Chart 2: Domain Weakness — count at each level per domain (1-3)
    domain_dist = {
        'Listening': Counter(), 'Speaking': Counter(),
        'Reading': Counter(), 'Writing': Counter(),
    }
    for latest in latest_by_student.values():
        if latest.listening_level: domain_dist['Listening'][latest.listening_level] += 1
        if latest.speaking_level: domain_dist['Speaking'][latest.speaking_level] += 1
        if latest.reading_level: domain_dist['Reading'][latest.reading_level] += 1
        if latest.writing_level: domain_dist['Writing'][latest.writing_level] += 1

    # Chart 3: Reclassification Pipeline (current ELs only)
    pipeline = Counter()
    for s in filtered:
        if s.el_status in ('Newcomer', 'LTEL'):
            latest = latest_by_student.get(s.id)
            if latest and latest.overall_level:
                pipeline[latest.overall_level] += 1

    # Chart 4: EL Status Breakdown
    el_status_dist = Counter(s.el_status or 'EO' for s in filtered)

    # Chart 5: Year-over-Year Growth (% of caseload at each Overall level per school year)
    # Use ALL ELPAC records for filtered students, not just latest
    all_scores = []
    if student_ids:
        all_scores = ELPACScore.query.filter(
            ELPACScore.student_id.in_(student_ids),
            ELPACScore.test_purpose == 'Summative',
            ELPACScore.overall_level.isnot(None),
        ).all()
    yoy = defaultdict(lambda: Counter())
    for sc in all_scores:
        if sc.school_year:
            yoy[sc.school_year][sc.overall_level] += 1

    # Chart 6: Years in US Schools Distribution (EL students only)
    years_dist = Counter()
    for s in filtered:
        if s.el_status in ('Newcomer', 'LTEL', 'RFEP'):
            years_dist[_years_in_us_schools_bucket(s)] += 1

    # Student detail table rows
    table_rows = []
    for s in filtered:
        latest = latest_by_student.get(s.id)
        prior = None
        if latest:
            # Find prior Summative
            summatives = [r for r in s.elpac_scores
                          if r.test_purpose == 'Summative' and r.id != latest.id]
            prior = summatives[0] if summatives else None
        growth = None
        if latest and latest.overall_scale and prior and prior.overall_scale:
            growth = latest.overall_scale - prior.overall_scale
        table_rows.append({
            's': s,
            'latest': latest,
            'growth': growth,
        })
    table_rows.sort(key=lambda r: (
        -(r['latest'].overall_level or 0) if r['latest'] else 0,
        r['s'].last_name or '',
    ))

    # Build filter dropdown options
    grade_options = sorted({s.grade_level for s in students if s.grade_level})
    cohort_options = sorted({s.graduation_year for s in students if s.graduation_year})

    # ── ELPI status + Reclassification Candidates ───────────────────
    # For each filtered student with a current Summative score, compute
    # both simplified and full ELPI status by comparing to their prior year.
    simplified_counts = Counter()
    full_counts = Counter()
    reclass_candidates = []          # students at PL 4 right now (not yet RFEP)
    elpi_per_student = {}            # student_id -> elpi dict
    big_movers = []                  # students who jumped 2+ levels (simplified or CDE)

    for s in filtered:
        summatives = [r for r in s.elpac_scores if r.test_purpose == 'Summative']
        # `elpac_scores` relationship is ordered by test_date DESC.
        if not summatives:
            continue
        current = summatives[0]
        prior = summatives[1] if len(summatives) > 1 else None

        elpi = compute_elpi(current, prior, s.el_status)
        elpi_per_student[s.id] = elpi
        if elpi['simplified_status'] not in ('No current score', 'No prior score'):
            simplified_counts[elpi['simplified_status']] += 1
            full_counts[elpi['full_status']] += 1

        # Reclassification candidate: scored 4 on the most recent test and
        # is NOT yet RFEP. Counselor needs to push reclass paperwork.
        if current.overall_level == 4 and s.el_status != 'RFEP':
            reclass_candidates.append({
                's': s,
                'current': current,
                'prior': prior,
                'is_new_at_4': elpi['is_new_at_4'],
                'elpi_now': elpi['elpi_now'],
                'elpi_prior': elpi['elpi_prior'],
            })

        # Big movers: 2+ level change in either direction (simplified PL or CDE ELPI rank).
        pl_jump = None
        if elpi['pl_now'] is not None and elpi['pl_prior'] is not None:
            pl_jump = elpi['pl_now'] - elpi['pl_prior']
        cde_jump = None
        rank_now = elpi_rank(elpi['elpi_now'])
        rank_prior = elpi_rank(elpi['elpi_prior'])
        if rank_now is not None and rank_prior is not None:
            cde_jump = rank_now - rank_prior
        if (pl_jump is not None and abs(pl_jump) >= 2) or (cde_jump is not None and abs(cde_jump) >= 2):
            big_movers.append({
                's': s,
                'current': current,
                'prior': prior,
                'pl_jump': pl_jump,
                'cde_jump': cde_jump,
                'elpi_now': elpi['elpi_now'],
                'elpi_prior': elpi['elpi_prior'],
            })

    # Sort candidates: newly-at-4 first, then by last name
    reclass_candidates.sort(key=lambda r: (
        0 if r['is_new_at_4'] else 1,
        (r['s'].last_name or '').lower(),
    ))

    # Sort big movers: gainers first (biggest jump up), then droppers
    # (biggest drop down). Within each group, sort by magnitude.
    def _mover_sort(r):
        biggest = max((r['pl_jump'] or 0), (r['cde_jump'] or 0), key=abs)
        # Direction first (positive before negative), then magnitude descending
        return (0 if biggest >= 0 else 1, -abs(biggest), (r['s'].last_name or '').lower())
    big_movers.sort(key=_mover_sort)

    # Attach ELPI to the existing student detail table
    for row in table_rows:
        row['elpi'] = elpi_per_student.get(row['s'].id)

    return render_template(
        'analytics/elpac.html',
        students=students,
        filtered_count=len(filtered),
        total_count=len(students),
        filters={
            'grade_level': grade, 'cohort': cohort,
            'el_status': el_status, 'years_in_us_schools': years_bucket,
        },
        grade_options=grade_options,
        cohort_options=cohort_options,
        overall_dist=dict(overall_dist),
        domain_dist={d: dict(c) for d, c in domain_dist.items()},
        pipeline=dict(pipeline),
        el_status_dist=dict(el_status_dist),
        yoy={yr: dict(c) for yr, c in yoy.items()},
        years_dist=dict(years_dist),
        years_buckets=YEARS_BUCKETS,
        table_rows=table_rows,
        reclass_candidates=reclass_candidates,
        simplified_counts=dict(simplified_counts),
        full_counts=dict(full_counts),
        simplified_categories=SIMPLIFIED_CATEGORIES,
        full_categories=FULL_CATEGORIES,
        big_movers=big_movers,
    )


# ── Data aggregation functions ────────────────────────────────────

def _caseload_data(students):
    """Grade level distribution and demographics."""
    grade_dist = {}
    iep_count = 0
    s504_count = 0
    newcomer_count = 0
    ltel_count = 0
    el_other_count = 0
    total = len(students)

    for s in students:
        gl = s.grade_level or 0
        grade_dist[gl] = grade_dist.get(gl, 0) + 1
        if s.iep_status:
            iep_count += 1
        if s.section_504:
            s504_count += 1
        el = (s.el_status or '').strip()
        if el == 'Newcomer':
            newcomer_count += 1
        elif el == 'LTEL':
            ltel_count += 1
        elif el in ('EL 1', 'EL 2', 'EL 3'):
            el_other_count += 1

    # Build demographics as non-exclusive counts (students can be in multiple)
    demo_labels = []
    demo_values = []
    if iep_count:
        demo_labels.append('IEP')
        demo_values.append(iep_count)
    if s504_count:
        demo_labels.append('504 Plan')
        demo_values.append(s504_count)
    if newcomer_count:
        demo_labels.append('Newcomer')
        demo_values.append(newcomer_count)
    if ltel_count:
        demo_labels.append('LTEL')
        demo_values.append(ltel_count)
    if el_other_count:
        demo_labels.append('EL (Other)')
        demo_values.append(el_other_count)

    return {
        'total': total,
        'grade_distribution': {
            'labels': [f'Grade {g}' for g in sorted(grade_dist.keys())],
            'values': [grade_dist[g] for g in sorted(grade_dist.keys())],
        },
        'demographics': {
            'labels': demo_labels,
            'values': demo_values,
        },
    }


def _academic_data(student_ids):
    """GPA distribution and failing grades by subject."""
    # Get most recent grades per student
    grades = GradeRecord.query.filter(
        GradeRecord.student_id.in_(student_ids)
    ).order_by(GradeRecord.school_year.desc(), GradeRecord.quarter.desc()).all()

    # GPA calculation per student
    student_gpas = {}
    student_grades_map = {}
    for g in grades:
        if g.student_id not in student_grades_map:
            student_grades_map[g.student_id] = []
        student_grades_map[g.student_id].append(g)

    gpa_buckets = {'4.0+': 0, '3.0-3.9': 0, '2.0-2.9': 0, '1.0-1.9': 0, '< 1.0': 0}
    for sid, sg in student_grades_map.items():
        points = [g.gpa_points for g in sg if g.gpa_points is not None]
        if not points:
            continue
        gpa = sum(points) / len(points)
        student_gpas[sid] = gpa
        if gpa >= 4.0:
            gpa_buckets['4.0+'] += 1
        elif gpa >= 3.0:
            gpa_buckets['3.0-3.9'] += 1
        elif gpa >= 2.0:
            gpa_buckets['2.0-2.9'] += 1
        elif gpa >= 1.0:
            gpa_buckets['1.0-1.9'] += 1
        else:
            gpa_buckets['< 1.0'] += 1

    # Failing grades by subject — separate F and D counts
    failing_f = {}
    failing_d = {}
    for g in grades:
        subj = g.subject_area or g.course_name or 'Unknown'
        if g.letter_grade == 'F':
            failing_f[subj] = failing_f.get(subj, 0) + 1
        elif g.letter_grade in ('D', 'D-', 'D+'):
            failing_d[subj] = failing_d.get(subj, 0) + 1

    # Combine and sort by total count descending
    all_subjects = set(list(failing_f.keys()) + list(failing_d.keys()))
    combined = [(s, failing_f.get(s, 0) + failing_d.get(s, 0)) for s in all_subjects]
    sorted_failing = sorted(combined, key=lambda x: -x[1])
    all_subjects_sorted = [f[0] for f in sorted_failing]

    return {
        'gpa_distribution': {
            'labels': list(gpa_buckets.keys()),
            'values': list(gpa_buckets.values()),
        },
        'failing_by_subject': {
            'labels': all_subjects_sorted,
            'f_values': [failing_f.get(s, 0) for s in all_subjects_sorted],
            'd_values': [failing_d.get(s, 0) for s in all_subjects_sorted],
        },
        'avg_gpa': round(sum(student_gpas.values()) / len(student_gpas), 2) if student_gpas else 0,
        'total_failing': sum(failing_f.values()) + sum(failing_d.values()),
    }


def _attendance_data(student_ids, start, end):
    """Absence rates and trends."""
    records = AttendanceRecord.query.filter(
        AttendanceRecord.student_id.in_(student_ids),
        AttendanceRecord.date >= start,
        AttendanceRecord.date <= end,
        # Daily attendance is imported with period NULL (not 0); == 0 matched
        # nothing, leaving the analytics charts silently empty. Accept both.
        db.or_(AttendanceRecord.period == 0, AttendanceRecord.period.is_(None)),
    ).all()

    # Monthly trend
    monthly = {}
    for r in records:
        key = r.date.strftime('%Y-%m')
        if key not in monthly:
            monthly[key] = {'present': 0, 'absent': 0, 'tardy': 0}
        if r.status == 'present':
            monthly[key]['present'] += 1
        elif r.status == 'absent':
            monthly[key]['absent'] += 1
        elif r.status == 'tardy':
            monthly[key]['tardy'] += 1

    sorted_months = sorted(monthly.keys())
    month_labels = []
    for m in sorted_months:
        parts = m.split('-')
        months = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        month_labels.append(months[int(parts[1])])

    # Per-student absence counts (top 10 most absent)
    student_absences = {}
    for r in records:
        if r.status == 'absent':
            student_absences[r.student_id] = student_absences.get(r.student_id, 0) + 1

    sorted_students = sorted(student_absences.items(), key=lambda x: -x[1])[:10]
    student_names = []
    student_abs_values = []
    for sid, count in sorted_students:
        s = Student.query.get(sid)
        if s:
            student_names.append(f'{s.first_name} {s.last_name[0]}.')
            student_abs_values.append(count)

    # Chronic absenteeism (10%+ absence rate)
    total_days = len(set(r.date for r in records)) or 1
    chronic_count = sum(1 for count in student_absences.values()
                        if count / total_days >= 0.10)

    return {
        'monthly_trend': {
            'labels': month_labels,
            'present': [monthly[m]['present'] for m in sorted_months],
            'absent': [monthly[m]['absent'] for m in sorted_months],
            'tardy': [monthly[m]['tardy'] for m in sorted_months],
        },
        'top_absent_students': {
            'labels': student_names,
            'values': student_abs_values,
        },
        'chronic_absenteeism_count': chronic_count,
        'chronic_absenteeism_pct': round(chronic_count / len(student_ids) * 100, 1) if student_ids else 0,
    }


def _services_data(uid, start, end):
    """Service delivery breakdown."""
    records = ServiceRecord.query.filter(
        ServiceRecord.counselor_id == uid,
        ServiceRecord.date >= start,
        ServiceRecord.date <= end,
    ).all()

    # By type
    by_type = {}
    for r in records:
        label = dict(ServiceRecord.SERVICE_TYPES).get(r.service_type, r.service_type)
        by_type[label] = by_type.get(label, 0) + 1

    sorted_types = sorted(by_type.items(), key=lambda x: -x[1])

    # By ASCA domain
    by_domain = {'Academic': 0, 'Career': 0, 'Social/Emotional': 0, 'Other': 0}
    for r in records:
        d = (r.asca_domain or '').lower()
        if 'academic' in d:
            by_domain['Academic'] += 1
        elif 'career' in d:
            by_domain['Career'] += 1
        elif 'social' in d or 'emotional' in d:
            by_domain['Social/Emotional'] += 1
        else:
            by_domain['Other'] += 1

    # Total hours
    total_minutes = sum(r.duration_minutes or 0 for r in records)

    # Referral rate
    referral_count = sum(1 for r in records if r.referral_made)

    return {
        'by_type': {
            'labels': [t[0] for t in sorted_types],
            'values': [t[1] for t in sorted_types],
        },
        'by_domain': {
            'labels': list(by_domain.keys()),
            'values': list(by_domain.values()),
        },
        'total_services': len(records),
        'total_hours': round(total_minutes / 60, 1),
        'referral_count': referral_count,
    }


def _activities_data(uid, start, end):
    """Use-of-time breakdown from activity log."""
    activities = Activity.query.filter(
        Activity.counselor_id == uid,
        Activity.date >= start,
        Activity.date <= end,
    ).all()

    # By service type (ASCA 4 quadrants)
    type_labels = dict(Activity.SERVICE_TYPES)
    by_type = {}
    for a in activities:
        label = type_labels.get(a.service_type, a.service_type)
        by_type[label] = by_type.get(label, 0) + (a.duration_minutes or 0)

    # By delivery type
    by_delivery = {}
    for a in activities:
        dt = a.delivery_type or 'unspecified'
        by_delivery[dt] = by_delivery.get(dt, 0) + 1

    # Weekly trend
    weekly = {}
    for a in activities:
        week = a.date.isocalendar()[1]
        year = a.date.year
        key = f'{year}-W{week:02d}'
        if key not in weekly:
            weekly[key] = 0
        weekly[key] += (a.duration_minutes or 0)

    sorted_weeks = sorted(weekly.keys())[-12:]  # last 12 weeks

    total_minutes = sum(a.duration_minutes or 0 for a in activities)
    total_students = sum(a.num_students or 0 for a in activities)

    return {
        'use_of_time': {
            'labels': list(by_type.keys()),
            'values': [round(v / 60, 1) for v in by_type.values()],
        },
        'by_delivery': {
            'labels': [d.replace('_', ' ').title() for d in by_delivery.keys()],
            'values': list(by_delivery.values()),
        },
        'weekly_hours': {
            'labels': [w.split('-')[1] for w in sorted_weeks],
            'values': [round(weekly[w] / 60, 1) for w in sorted_weeks],
        },
        'total_hours': round(total_minutes / 60, 1),
        'total_activities': len(activities),
        'total_students_served': total_students,
    }


def _contacts_over_time(uid, start, end):
    """Student contacts (notes) over time."""
    notes = Note.query.filter(
        Note.author_id == uid,
        Note.session_date >= start,
        Note.session_date <= end,
    ).all()

    # Weekly contact counts
    weekly = {}
    for n in notes:
        if not n.session_date:
            continue
        week = n.session_date.isocalendar()[1]
        year = n.session_date.year
        key = f'{year}-W{week:02d}'
        weekly[key] = weekly.get(key, 0) + 1

    sorted_weeks = sorted(weekly.keys())[-12:]

    # By note type
    by_type = {}
    for n in notes:
        by_type[n.note_type or 'other'] = by_type.get(n.note_type or 'other', 0) + 1

    sorted_types = sorted(by_type.items(), key=lambda x: -x[1])[:8]

    # Unique students contacted
    unique_students = len(set(n.student_id for n in notes if n.student_id))

    return {
        'weekly_contacts': {
            'labels': [w.split('-')[1] for w in sorted_weeks],
            'values': [weekly[w] for w in sorted_weeks],
        },
        'by_type': {
            'labels': [t[0].replace('_', ' ').title() for t in sorted_types],
            'values': [t[1] for t in sorted_types],
        },
        'total_notes': len(notes),
        'unique_students': unique_students,
    }


def _followup_data(uid):
    """Follow-up completion rates."""
    total = Note.query.filter(
        Note.author_id == uid,
        Note.follow_up_needed == True,
    ).count()

    completed = Note.query.filter(
        Note.author_id == uid,
        Note.follow_up_needed == True,
        Note.follow_up_completed == True,
    ).count()

    overdue = Note.query.filter(
        Note.author_id == uid,
        Note.follow_up_needed == True,
        Note.follow_up_date < date.today(),
        db.or_(Note.follow_up_completed == False, Note.follow_up_completed.is_(None)),
    ).count()

    pending = total - completed - overdue

    return {
        'total': total,
        'completed': completed,
        'overdue': overdue,
        'pending': max(0, pending),
        'completion_rate': round(completed / total * 100, 1) if total else 0,
    }
