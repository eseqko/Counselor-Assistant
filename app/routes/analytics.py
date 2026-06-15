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
# Per the counselor: F, NP (No Pass in P/NP courses), and NM (No Mark in P/NP
# courses) all count as a failing outcome. _FAIL is the failing-letter set used
# for the Fail count and % Fail; _DF additionally includes D-/D/D+ for the
# total "struggling" set and the % D/F column.
_FAIL = {'F', 'NP', 'NM'}
_NEAR_FAILING = {'D+', 'D', 'D-'}
_DF = _FAIL | _NEAR_FAILING


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

    # Student-name lookup for the per-course D/F list column.
    name_by_id = {s.id: f'{s.first_name} {s.last_name}'
                  for s in Student.query.filter(Student.id.in_(student_ids)).all()}

    # Per-course aggregates.
    #   fail        = count of F+NP+NM grades issued (the user's "Fail" column)
    #   d           = count of D-/D/D+ grades issued
    #   total       = total grade records issued in this class
    #   all_students    = unique students who got ANY grade here (class size denominator)
    #   students_fail   = unique students with ≥1 F/NP/NM (% Fail numerator)
    #   students_df     = unique students with ≥1 D/F/NP/NM (% D/F numerator)
    #   df_list     = (sid, letter) tuples for the collapsible D/F List column
    by_course = defaultdict(lambda: {'fail': 0, 'd': 0, 'total': 0,
                                     'all_students': set(),
                                     'students_fail': set(),
                                     'students_df': set(),
                                     'df_list': []})
    by_teacher = defaultdict(lambda: {'fail': 0, 'd': 0, 'total': 0,
                                     'all_students': set(),
                                     'students_fail': set(),
                                     'students_df': set()})
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
        elif lg in _FAIL: dist['F'] += 1
        elif lg == 'P': dist['P/NP'] += 1
        elif lg: dist['Other'] += 1

        course = (g.course_name or 'Unknown').strip()
        teacher = (g.teacher or '').strip()
        by_course[course]['total'] += 1
        # Every student appearing in the class — denominator for the % columns.
        by_course[course]['all_students'].add(g.student_id)
        if teacher:
            by_teacher[teacher]['total'] += 1
            by_teacher[teacher]['all_students'].add(g.student_id)
        if g.period is not None:
            by_period[g.period]['total'] += 1

        is_fail = lg in _FAIL
        is_df = lg in _DF
        if is_df:
            total_df += 1
            per_student_df[g.student_id] += 1
            failing_students.add(g.student_id)
            by_course[course]['students_df'].add(g.student_id)
            by_course[course]['df_list'].append((g.student_id, lg))
            if g.period is not None:
                by_period[g.period]['df'] += 1
            subj = g.subject_area or course or 'Unknown'
            if is_fail:
                by_course[course]['fail'] += 1
                by_course[course]['students_fail'].add(g.student_id)
                by_subject[subj]['f'] += 1
            else:
                by_course[course]['d'] += 1
                by_subject[subj]['d'] += 1
            if teacher:
                by_teacher[teacher]['students_df'].add(g.student_id)
                if is_fail:
                    by_teacher[teacher]['fail'] += 1
                    by_teacher[teacher]['students_fail'].add(g.student_id)
                else:
                    by_teacher[teacher]['d'] += 1

    # D/F by course — rank by total D/F, then by % D/F (student-based)
    course_rows = []
    for name, c in by_course.items():
        df_count = c['fail'] + c['d']
        if df_count == 0:
            continue
        class_size = len(c['all_students']) or 1
        # Per-student rosters for the "D/F List" column — one entry per student
        # showing their worst grade in the class (multiple D/F across quarters
        # collapse to the lowest). NP and NM rank just after literal F.
        worst = {}
        WORST_RANK = {'F': 0, 'NP': 1, 'NM': 1, 'D-': 2, 'D': 3, 'D+': 4}
        for sid, letter in c['df_list']:
            if sid not in worst or WORST_RANK.get(letter, 9) < WORST_RANK.get(worst[sid], 9):
                worst[sid] = letter
        df_students = sorted(
            [{'id': sid, 'name': name_by_id.get(sid, f'Student #{sid}'),
              'letter': worst[sid]} for sid in worst],
            key=lambda r: (WORST_RANK.get(r['letter'], 9), r['name'].lower()),
        )
        course_rows.append({
            'course': name,
            'fail': c['fail'],
            'd': c['d'],
            'df': df_count,
            'class_size': class_size,
            'students_fail': len(c['students_fail']),
            'students_df': len(c['students_df']),
            'fail_pct': round(len(c['students_fail']) / class_size * 100, 1),
            'df_pct': round(len(c['students_df']) / class_size * 100, 1),
            'df_students': df_students,
        })
    course_rows.sort(key=lambda r: (-r['df'], -r['df_pct']))
    top_courses = course_rows[:15]

    # D/F by teacher — same shape as by course
    # School-wide D/F rate across all teachers — the benchmark for flagging
    # teachers whose rate is well above average. Requires ≥10 grades issued
    # by the teacher to avoid flagging on small samples (a teacher with 3
    # grades, 2 D/F = 67%, isn't a meaningful signal).
    total_teacher_grades = sum(c['total'] for c in by_teacher.values()) or 1
    total_teacher_df = sum(c['fail'] + c['d'] for c in by_teacher.values())
    school_df_rate = round(total_teacher_df / total_teacher_grades * 100, 1)
    OUTLIER_MULT = 1.5      # rate must exceed school_avg × 1.5 to flag
    MIN_SAMPLE = 10         # AND teacher must have ≥10 grades issued
    teacher_rows = []
    for name, c in by_teacher.items():
        df = c['fail'] + c['d']
        if df == 0:
            continue
        rate = round(df / c['total'] * 100, 1) if c['total'] else 0
        teacher_rows.append({
            'teacher': name, 'df': df, 'fail': c['fail'], 'd': c['d'],
            'students': len(c['students_df']), 'total': c['total'],
            'rate': rate,
            'is_outlier': (
                c['total'] >= MIN_SAMPLE and rate >= school_df_rate * OUTLIER_MULT
                and school_df_rate > 0
            ),
        })
    teacher_rows.sort(key=lambda r: (-r['rate'], -r['df']))
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
            'f_values': [r['fail'] for r in top_courses],
            'd_values': [r['d'] for r in top_courses],
            'rows': course_rows,
        },
        'df_by_period': period_payload,
        'df_by_subject': subj_payload,
        'df_by_teacher': {
            'labels': [r['teacher'] for r in top_teachers],
            'f_values': [r['fail'] for r in top_teachers],
            'd_values': [r['d'] for r in top_teachers],
            'rows': teacher_rows,
            'has_data': bool(by_teacher),
            'school_avg_rate': school_df_rate,
            'outlier_multiplier': OUTLIER_MULT,
            'min_sample': MIN_SAMPLE,
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


# ── EL Outcomes report ───────────────────────────────────────────

# Subgroup keys used across the report. Order matters — drives display order.
_EL_GROUPS = ['newcomer', 'ltel', 'rfep', 'eo', 'unknown']
_EL_GROUP_LABELS = {
    'newcomer': 'Newcomer',
    'ltel': 'LTEL',
    'rfep': 'Reclassified (RFEP)',
    'eo': 'English Only',
    'unknown': 'EL — duration unknown',
}


def _classify_el_subgroup(student, ltel_threshold=5):
    """Classify each student into one of: newcomer / ltel / rfep / eo / unknown.

    "Newcomer" is operationally defined as an EL student with fewer than
    `ltel_threshold` years in US schools (default 5 per the counselor's
    working definition; CDE's formal LTEL line is 6+). A student formally
    tagged el_status='LTEL' always classifies as LTEL regardless of years.
    Returns None for non-EL/non-RFEP/non-EO cases (very rare).
    """
    el = (student.el_status or '').strip()
    if el == 'RFEP':
        return 'rfep'
    if el in ('', 'EO'):
        return 'eo'
    if el == 'LTEL':
        return 'ltel'
    # Remaining: an active EL student (Newcomer / EL 1-3). Bucket by duration.
    yrs = student.years_in_us_schools
    if yrs is None:
        return 'unknown'
    return 'newcomer' if yrs < ltel_threshold else 'ltel'


@analytics_bp.route('/el-outcomes')
@login_required
def el_outcomes():
    """EL subgroup outcomes: Newcomer vs LTEL vs RFEP attendance + grades.

    Uses each student's US School Entry Date + EL status to bucket them, then
    surfaces (1) demographic spread, (2) attendance comparisons, (3) academic
    performance, (4) classes where each subgroup struggles most, (5) the
    high-risk overlap split by subgroup.
    """
    return render_template('analytics/el_outcomes.html')


@analytics_bp.route('/api/el-outcomes')
@login_required
def api_el_outcomes():
    """Data payload for the EL Outcomes page."""
    uid = current_user.id
    today = date.today()

    try:
        ltel_threshold = int(request.args.get('threshold', 5))
    except ValueError:
        ltel_threshold = 5
    ltel_threshold = max(1, min(ltel_threshold, 10))

    students = Student.query.filter_by(
        assigned_counselor_id=uid, status='active').all()
    if not students:
        return jsonify({'empty': True})

    # Group every active student.
    subgroup = {s.id: _classify_el_subgroup(s, ltel_threshold) for s in students}
    by_group_ids = defaultdict(list)
    for sid, g in subgroup.items():
        if g:
            by_group_ids[g].append(sid)

    # Composition + average years-in-US per group.
    years_by_group = defaultdict(list)
    for s in students:
        if s.years_in_us_schools is not None:
            years_by_group[subgroup[s.id]].append(s.years_in_us_schools)
    composition = []
    for g in _EL_GROUPS:
        if not by_group_ids.get(g):
            continue
        years_list = years_by_group.get(g, [])
        composition.append({
            'group': g,
            'label': _EL_GROUP_LABELS[g],
            'count': len(by_group_ids[g]),
            'avg_years_us': round(sum(years_list) / len(years_list), 1) if years_list else None,
        })

    # School-year filter for grades. Default to the most recent year present.
    student_ids = [s.id for s in students]
    years = sorted({y[0] for y in db.session.query(GradeRecord.school_year)
                    .filter(GradeRecord.student_id.in_(student_ids),
                            GradeRecord.school_year.isnot(None)).distinct().all()},
                   reverse=True)
    year = request.args.get('year') or (years[0] if years else None)
    grades = []
    if year:
        grades = GradeRecord.query.filter(
            GradeRecord.student_id.in_(student_ids),
            GradeRecord.school_year == year,
            GradeRecord.grade_type == 'final',
        ).all()

    # Attendance covers the last 365 days, matching Insights 360.
    attend_start = today - timedelta(days=365)
    attendance = AttendanceRecord.query.filter(
        AttendanceRecord.student_id.in_(student_ids),
        AttendanceRecord.date >= attend_start,
        AttendanceRecord.date <= today,
    ).all()

    # ── Attendance aggregates ──
    per_student_absent = defaultdict(int)
    per_student_total = defaultdict(int)
    per_student_tardy = defaultdict(int)
    days_seen = defaultdict(set)
    period_absent = defaultdict(lambda: defaultdict(int))  # group -> period -> count
    for r in attendance:
        st = (r.status or '').lower()
        per_student_total[r.student_id] += 1
        days_seen[r.student_id].add(r.date)
        if st == 'absent':
            per_student_absent[r.student_id] += 1
            g = subgroup.get(r.student_id)
            if g and r.period is not None and r.period >= 1:
                period_absent[g][r.period] += 1
        elif st == 'tardy':
            per_student_tardy[r.student_id] += 1

    attend_summary = []
    for g in _EL_GROUPS:
        ids = by_group_ids.get(g, [])
        if not ids:
            continue
        total_abs = sum(per_student_absent.get(sid, 0) for sid in ids)
        total_records = sum(per_student_total.get(sid, 0) for sid in ids)
        total_tardy = sum(per_student_tardy.get(sid, 0) for sid in ids)
        # Chronic absenteeism: ≥10% of distinct enrolled days missed (Attendance
        # Works / federal ESSA definition).
        chronic = 0
        for sid in ids:
            ds = len(days_seen.get(sid, set())) or 1
            if per_student_absent.get(sid, 0) / ds >= 0.10:
                chronic += 1
        attend_summary.append({
            'group': g,
            'label': _EL_GROUP_LABELS[g],
            'count': len(ids),
            'total_absences': total_abs,
            'avg_absences_per_student': round(total_abs / len(ids), 1),
            'total_tardies': total_tardy,
            'chronic_count': chronic,
            'chronic_rate': round(chronic / len(ids) * 100, 1),
            'absence_rate': round(total_abs / total_records * 100, 1) if total_records else 0.0,
        })

    # Period-level absences chart: one bar per group at each period.
    period_set = sorted({p for g in period_absent.values() for p in g.keys()})
    period_chart = {
        'periods': [f'Period {p}' for p in period_set],
        'series': [
            {
                'group': g,
                'label': _EL_GROUP_LABELS[g],
                'values': [period_absent[g].get(p, 0) for p in period_set],
            }
            for g in _EL_GROUPS if by_group_ids.get(g) and period_absent.get(g)
        ],
    }

    # ── Academic aggregates ──
    GPA_MAP = {'A+': 4.0, 'A': 4.0, 'A-': 3.7, 'B+': 3.3, 'B': 3.0, 'B-': 2.7,
               'C+': 2.3, 'C': 2.0, 'C-': 1.7, 'D+': 1.3, 'D': 1.0, 'D-': 0.7,
               'F': 0.0}
    per_student_df = defaultdict(int)
    per_student_gpa_points = defaultdict(list)
    grades_by_group_letter = defaultdict(lambda: Counter())
    # course key (course, period) -> group -> {'df', 'total', 'students'}
    course_by_group = defaultdict(lambda: defaultdict(lambda: {'df': 0, 'total': 0, 'students': set()}))
    # teacher -> group -> {'df', 'total', 'students'} for the teacher-outlier view
    teacher_by_group = defaultdict(lambda: defaultdict(lambda: {'df': 0, 'total': 0, 'students': set()}))
    for grec in grades:
        g = subgroup.get(grec.student_id)
        if not g:
            continue
        lg = (grec.letter_grade or '').strip()
        # GPA letter spread (A/B/C/D/F)
        if lg in ('A+', 'A', 'A-'): grades_by_group_letter[g]['A'] += 1
        elif lg in ('B+', 'B', 'B-'): grades_by_group_letter[g]['B'] += 1
        elif lg in ('C+', 'C', 'C-'): grades_by_group_letter[g]['C'] += 1
        elif lg in ('D+', 'D', 'D-'): grades_by_group_letter[g]['D'] += 1
        elif lg in ('F', 'NP'): grades_by_group_letter[g]['F'] += 1
        # GPA points
        if lg in GPA_MAP:
            per_student_gpa_points[grec.student_id].append(GPA_MAP[lg])
        # D/F tallying
        is_df = lg in _DF
        course_key = (grec.course_name or 'Unknown', grec.period)
        course_by_group[course_key][g]['total'] += 1
        course_by_group[course_key][g]['students'].add(grec.student_id)
        teacher_name = (grec.teacher or '').strip()
        if teacher_name:
            teacher_by_group[teacher_name][g]['total'] += 1
            teacher_by_group[teacher_name][g]['students'].add(grec.student_id)
        if is_df:
            per_student_df[grec.student_id] += 1
            course_by_group[course_key][g]['df'] += 1
            if teacher_name:
                teacher_by_group[teacher_name][g]['df'] += 1

    # Per-group GPA average + D/F per student
    academic_summary = []
    for g in _EL_GROUPS:
        ids = by_group_ids.get(g, [])
        if not ids:
            continue
        gpa_vals = []
        for sid in ids:
            pts = per_student_gpa_points.get(sid, [])
            if pts:
                gpa_vals.append(sum(pts) / len(pts))
        total_df = sum(per_student_df.get(sid, 0) for sid in ids)
        students_with_df = sum(1 for sid in ids if per_student_df.get(sid, 0) >= 1)
        academic_summary.append({
            'group': g,
            'label': _EL_GROUP_LABELS[g],
            'count': len(ids),
            'avg_gpa': round(sum(gpa_vals) / len(gpa_vals), 2) if gpa_vals else None,
            'total_df': total_df,
            'avg_df_per_student': round(total_df / len(ids), 2),
            'students_with_df': students_with_df,
            'students_with_df_pct': round(students_with_df / len(ids) * 100, 1),
        })

    # Letter-grade distribution per group (for stacked-bar chart)
    letters_order = ['A', 'B', 'C', 'D', 'F']
    letter_dist = []
    for g in _EL_GROUPS:
        counts = grades_by_group_letter.get(g)
        if not counts:
            continue
        total = sum(counts.values()) or 1
        letter_dist.append({
            'group': g,
            'label': _EL_GROUP_LABELS[g],
            'values': [counts.get(L, 0) for L in letters_order],
            'pct': [round(counts.get(L, 0) / total * 100, 1) for L in letters_order],
        })

    # ── Classes where each subgroup struggles most ──
    # For each (course, period), compute per-group D/F rate. Then surface top
    # classes for Newcomers, top for LTELs, plus the intersection where BOTH
    # subgroups fail at high rates (≥25% of grades issued + 3+ D/F).
    def _course_rows(group_key, min_total=5, min_df=3):
        rows = []
        for (course, period), per_g in course_by_group.items():
            cell = per_g.get(group_key)
            if not cell or cell['total'] < min_total or cell['df'] < min_df:
                continue
            rows.append({
                'course': course, 'period': period,
                'df': cell['df'], 'total': cell['total'],
                'students': len(cell['students']),
                'rate': round(cell['df'] / cell['total'] * 100, 1),
            })
        rows.sort(key=lambda r: (-r['rate'], -r['df']))
        return rows[:15]

    classes_newcomer = _course_rows('newcomer')
    classes_ltel = _course_rows('ltel')

    # Teachers whose classes generate disproportionate D/F for each subgroup.
    # Require ≥5 grades to a subgroup AND ≥3 D/F before listing — small samples
    # produce misleading rates ("100% fail rate" off 1 grade isn't a signal).
    def _teacher_rows(group_key, min_total=5, min_df=3):
        rows = []
        for teacher, per_g in teacher_by_group.items():
            cell = per_g.get(group_key)
            if not cell or cell['total'] < min_total or cell['df'] < min_df:
                continue
            rows.append({
                'teacher': teacher,
                'df': cell['df'], 'total': cell['total'],
                'students': len(cell['students']),
                'rate': round(cell['df'] / cell['total'] * 100, 1),
            })
        rows.sort(key=lambda r: (-r['rate'], -r['df']))
        return rows[:15]

    teachers_newcomer = _teacher_rows('newcomer')
    teachers_ltel = _teacher_rows('ltel')

    # Teachers struggling with BOTH subgroups (the intersection list)
    nc_teacher_set = {r['teacher'] for r in teachers_newcomer}
    lt_teacher_set = {r['teacher'] for r in teachers_ltel}
    shared_teachers = nc_teacher_set & lt_teacher_set
    teachers_both = []
    for t_name in shared_teachers:
        nc = next((r for r in teachers_newcomer if r['teacher'] == t_name), None)
        lt = next((r for r in teachers_ltel if r['teacher'] == t_name), None)
        if nc and lt:
            teachers_both.append({
                'teacher': t_name,
                'newcomer_df': nc['df'], 'newcomer_rate': nc['rate'],
                'newcomer_students': nc['students'],
                'ltel_df': lt['df'], 'ltel_rate': lt['rate'],
                'ltel_students': lt['students'],
            })
    teachers_both.sort(key=lambda r: -(r['newcomer_rate'] + r['ltel_rate']))

    # Intersection: courses with high D/F for both Newcomers AND LTELs.
    nc_set = {(r['course'], r['period']) for r in classes_newcomer}
    lt_set = {(r['course'], r['period']) for r in classes_ltel}
    shared_keys = nc_set & lt_set
    classes_both = []
    for key in shared_keys:
        course, period = key
        nc = next((r for r in classes_newcomer if (r['course'], r['period']) == key), None)
        lt = next((r for r in classes_ltel if (r['course'], r['period']) == key), None)
        if nc and lt:
            classes_both.append({
                'course': course, 'period': period,
                'newcomer_df': nc['df'], 'newcomer_rate': nc['rate'], 'newcomer_students': nc['students'],
                'ltel_df': lt['df'], 'ltel_rate': lt['rate'], 'ltel_students': lt['students'],
            })
    classes_both.sort(key=lambda r: -(r['newcomer_rate'] + r['ltel_rate']))

    # ── Compounding risk by subgroup ──
    # Same metric as Insights 360 (≥2 D/F AND ≥5 absences) but bucketed.
    name_by_id = {s.id: s for s in students}
    compounding_by_group = defaultdict(list)
    for sid, s in name_by_id.items():
        df = per_student_df.get(sid, 0)
        absent = per_student_absent.get(sid, 0)
        if df >= 2 and absent >= 5:
            g = subgroup.get(sid)
            if g:
                compounding_by_group[g].append({
                    'id': sid,
                    'name': f'{s.first_name} {s.last_name}',
                    'grade': s.grade_level,
                    'df_count': df,
                    'absences': absent,
                    'years_us': s.years_in_us_schools,
                })
    for ids in compounding_by_group.values():
        ids.sort(key=lambda r: -(r['df_count'] + r['absences']))

    compounding_summary = []
    for g in _EL_GROUPS:
        ids = by_group_ids.get(g, [])
        flagged = compounding_by_group.get(g, [])
        if not ids:
            continue
        compounding_summary.append({
            'group': g,
            'label': _EL_GROUP_LABELS[g],
            'count': len(ids),
            'flagged': len(flagged),
            'rate': round(len(flagged) / len(ids) * 100, 1),
            'students': flagged[:25],
        })

    return jsonify({
        'filters': {
            'year': year, 'years': years,
            'ltel_threshold': ltel_threshold,
        },
        'composition': composition,
        'attendance': {
            'summary': attend_summary,
            'by_period': period_chart,
        },
        'academic': {
            'summary': academic_summary,
            'letter_dist': {
                'letters': letters_order,
                'groups': letter_dist,
            },
        },
        'classes': {
            'newcomer': classes_newcomer,
            'ltel': classes_ltel,
            'both': classes_both,
        },
        'teachers': {
            'newcomer': teachers_newcomer,
            'ltel': teachers_ltel,
            'both': teachers_both,
            'has_data': bool(teacher_by_group),
        },
        'compounding': compounding_summary,
    })


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
