from flask import Blueprint, render_template, request, redirect, url_for
from flask_login import login_required, current_user
from app import db
from app.models.activity import Activity
from app.models.note import Note
from app.models.service_record import ServiceRecord
from app.models.student import Student
from app.models.attendance import AttendanceRecord
from app.models.grade import GradeRecord
from app.models.transcript import TranscriptRecord
from app.utils.audit import log_action
from app.utils.helpers import parse_date, current_school_year
from app.utils.security import csv_safe
from app.utils.roles import owned_or_404
from datetime import date, timedelta
from collections import defaultdict
from sqlalchemy import func

reports_bp = Blueprint('reports', __name__)


@reports_bp.route('/')
@login_required
def index():
    return render_template('reports/index.html')


@reports_bp.route('/use-of-time')
@login_required
def use_of_time():
    """ASCA Use-of-Time analysis - mirrors SCUTA's core report."""
    date_from = parse_date(request.args.get('date_from')) or (date.today() - timedelta(days=30))
    date_to = parse_date(request.args.get('date_to')) or date.today()

    activities = Activity.query.filter(
        Activity.counselor_id == current_user.id,
        Activity.date >= date_from,
        Activity.date <= date_to
    ).all()

    # Calculate time by service type
    time_by_type = defaultdict(int)
    time_by_category = defaultdict(int)
    time_by_day = defaultdict(lambda: defaultdict(int))

    for a in activities:
        mins = a.duration_minutes or 0
        time_by_type[a.service_type] += mins
        if a.category:
            time_by_category[a.category] += mins
        time_by_day[a.date.isoformat()][a.service_type] += mins

    total_minutes = sum(time_by_type.values())

    # Percentages
    percentages = {}
    for stype, mins in time_by_type.items():
        percentages[stype] = round((mins / total_minutes * 100), 1) if total_minutes > 0 else 0

    log_action('view', 'report', details='Use of Time Report')

    return render_template('reports/use_of_time.html',
        date_from=date_from, date_to=date_to,
        time_by_type=dict(time_by_type),
        time_by_category=dict(time_by_category),
        percentages=percentages,
        total_minutes=total_minutes,
        service_types=Activity.SERVICE_TYPES,
        activities=activities)


@reports_bp.route('/student-services')
@login_required
def student_services():
    """Student Service Report - services delivered per student."""
    student_id = request.args.get('student_id', '')
    date_from = parse_date(request.args.get('date_from')) or (date.today() - timedelta(days=90))
    date_to = parse_date(request.args.get('date_to')) or date.today()

    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active'
    ).order_by(Student.last_name).all()

    records = []
    selected_student = None
    if student_id:
        # Ownership-scoped: the dropdown only lists caseload students, but the
        # student_id arrives via query string — never resolve a foreign or shadow
        # student's name/records from a tampered URL (404, no IDOR enumeration).
        selected_student = owned_or_404(Student, int(student_id),
                                        owner_attr='assigned_counselor_id')
        records = ServiceRecord.query.filter(
            ServiceRecord.student_id == int(student_id),
            ServiceRecord.date >= date_from,
            ServiceRecord.date <= date_to
        ).order_by(ServiceRecord.date.desc()).all()

    # Summary stats
    total_sessions = len(records)
    total_minutes = sum(r.duration_minutes or 0 for r in records)
    by_type = defaultdict(int)
    for r in records:
        by_type[r.service_type] += 1

    log_action('view', 'report', details='Student Services Report')

    return render_template('reports/student_services.html',
        students=students, student_id=student_id,
        selected_student=selected_student,
        records=records, date_from=date_from, date_to=date_to,
        total_sessions=total_sessions, total_minutes=total_minutes,
        by_type=dict(by_type))


@reports_bp.route('/activity-summary')
@login_required
def activity_summary():
    """Activity Summary Report."""
    date_from = parse_date(request.args.get('date_from')) or (date.today() - timedelta(days=30))
    date_to = parse_date(request.args.get('date_to')) or date.today()

    activities = Activity.query.filter(
        Activity.counselor_id == current_user.id,
        Activity.date >= date_from,
        Activity.date <= date_to
    ).order_by(Activity.date.desc()).all()

    log_action('view', 'report', details='Activity Summary Report')

    return render_template('reports/activity_summary.html',
        activities=activities, date_from=date_from, date_to=date_to)


@reports_bp.route('/caseload-summary')
@login_required
def caseload_summary():
    """Caseload Summary - demographics and stats."""
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active').all()

    # Grade distribution
    by_grade = defaultdict(int)
    by_gender = defaultdict(int)
    by_ethnicity = defaultdict(int)
    iep_count = 0
    section_504_count = 0
    ell_count = 0

    for s in students:
        if s.grade_level:
            by_grade[s.grade_level] += 1
        if s.gender:
            by_gender[s.gender] += 1
        if s.ethnicity:
            by_ethnicity[s.ethnicity] += 1
        if s.iep_status:
            iep_count += 1
        if s.section_504:
            section_504_count += 1
        if s.ell_status:
            ell_count += 1

    log_action('view', 'report', details='Caseload Summary Report')

    return render_template('reports/caseload_summary.html',
        total_students=len(students),
        by_grade=dict(sorted(by_grade.items())),
        by_gender=dict(by_gender),
        by_ethnicity=dict(by_ethnicity),
        iep_count=iep_count, section_504_count=section_504_count,
        ell_count=ell_count)


@reports_bp.route('/topic-delivery')
@login_required
def topic_delivery():
    """Topic Delivery Log - frequency of topic coverage."""
    date_from = parse_date(request.args.get('date_from')) or (date.today() - timedelta(days=90))
    date_to = parse_date(request.args.get('date_to')) or date.today()

    # From activities
    activities = Activity.query.filter(
        Activity.counselor_id == current_user.id,
        Activity.date >= date_from,
        Activity.date <= date_to,
        Activity.topic != ''
    ).all()

    topic_counts = defaultdict(lambda: {'count': 0, 'total_minutes': 0, 'students': 0})
    for a in activities:
        if a.topic:
            topic_counts[a.topic]['count'] += 1
            topic_counts[a.topic]['total_minutes'] += a.duration_minutes or 0
            topic_counts[a.topic]['students'] += a.num_students or 0

    log_action('view', 'report', details='Topic Delivery Report')

    return render_template('reports/topic_delivery.html',
        topic_counts=dict(topic_counts),
        date_from=date_from, date_to=date_to)


# =====================================================================
#  EARLY WARNING REPORT
# =====================================================================

@reports_bp.route('/early-warning')
@login_required
def early_warning():
    """Early Warning Dashboard — automated student risk flags."""
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active'
    ).order_by(Student.last_name).all()

    today = date.today()
    thirty_days_ago = today - timedelta(days=30)

    student_ids = [s.id for s in students]

    # ── Bulk pre-fetch: attendance counts by student+status (1 query) ──
    att_counts_raw = db.session.query(
        AttendanceRecord.student_id,
        AttendanceRecord.status,
        func.count(AttendanceRecord.id)
    ).filter(
        AttendanceRecord.student_id.in_(student_ids),
        AttendanceRecord.date >= thirty_days_ago
    ).group_by(AttendanceRecord.student_id, AttendanceRecord.status).all()

    att_counts = defaultdict(lambda: defaultdict(int))  # {sid: {status: count}}
    att_totals = defaultdict(int)
    for sid, status, cnt in att_counts_raw:
        att_counts[sid][status] = cnt
        att_totals[sid] += cnt

    # ── Bulk pre-fetch: recent grades per student (1 query) ──
    all_recent_grades = GradeRecord.query.filter(
        GradeRecord.student_id.in_(student_ids)
    ).order_by(GradeRecord.school_year.desc(), GradeRecord.quarter.desc()).all()

    grades_by_student = defaultdict(list)
    for g in all_recent_grades:
        if len(grades_by_student[g.student_id]) < 8:
            grades_by_student[g.student_id].append(g)

    # ── Bulk pre-fetch: latest transcript per student (1 query) ──
    all_transcripts = TranscriptRecord.query.filter(
        TranscriptRecord.student_id.in_(student_ids)
    ).order_by(TranscriptRecord.created_at.desc()).all()

    transcripts_by_student = {}
    for tr in all_transcripts:
        if tr.student_id not in transcripts_by_student:
            transcripts_by_student[tr.student_id] = tr

    # ── Bulk pre-fetch: crisis note counts (1 query) ──
    crisis_raw = db.session.query(
        Note.student_id, func.count(Note.id)
    ).filter(
        Note.student_id.in_(student_ids),
        Note.note_type == 'crisis',
        Note.session_date >= thirty_days_ago
    ).group_by(Note.student_id).all()
    crisis_counts = dict(crisis_raw)

    # ── Bulk pre-fetch: overdue follow-up counts (1 query) ──
    overdue_raw = db.session.query(
        Note.student_id, func.count(Note.id)
    ).filter(
        Note.student_id.in_(student_ids),
        Note.follow_up_needed == True,
        Note.follow_up_date < today
    ).group_by(Note.student_id).all()
    overdue_counts = dict(overdue_raw)

    # ── Bulk pre-fetch: last note date per student (1 query) ──
    last_note_raw = db.session.query(
        Note.student_id, func.max(Note.session_date)
    ).filter(
        Note.student_id.in_(student_ids)
    ).group_by(Note.student_id).all()
    last_note_dates = dict(last_note_raw)

    # ── Bulk pre-fetch: last service date per student (1 query) ──
    last_svc_raw = db.session.query(
        ServiceRecord.student_id, func.max(ServiceRecord.date)
    ).filter(
        ServiceRecord.student_id.in_(student_ids)
    ).group_by(ServiceRecord.student_id).all()
    last_svc_dates = dict(last_svc_raw)

    flagged_students = []

    for s in students:
        flags = []
        severity = 0  # 0=none, 1=watch, 2=concern, 3=critical

        # --- Attendance flags (from pre-fetched counts) ---
        absences_30 = att_counts[s.id].get('absent', 0)
        tardies_30 = att_counts[s.id].get('tardy', 0)
        total_att_30 = att_totals[s.id]

        if absences_30 >= 5:
            flags.append(('Chronic Absence', f'{absences_30} absences in 30 days', 'danger'))
            severity = max(severity, 3)
        elif absences_30 >= 3:
            flags.append(('Attendance Concern', f'{absences_30} absences in 30 days', 'warning'))
            severity = max(severity, 2)

        if tardies_30 >= 5:
            flags.append(('Frequent Tardies', f'{tardies_30} tardies in 30 days', 'warning'))
            severity = max(severity, 2)

        # Attendance rate
        if total_att_30 > 0:
            present_30 = att_counts[s.id].get('present', 0)
            att_rate = round(present_30 / total_att_30 * 100, 1)
            if att_rate < 90:
                flags.append(('Low Attendance Rate', f'{att_rate}% (below 90% threshold)', 'danger'))
                severity = max(severity, 3)

        # --- Grade flags (from pre-fetched grades) ---
        recent_grades = grades_by_student.get(s.id, [])

        failing_courses = [g for g in recent_grades if g.letter_grade in ('F', 'D', 'D-', 'D+', 'NP')]
        f_grades = [g for g in recent_grades if g.letter_grade in ('F', 'NP')]

        if len(f_grades) >= 2:
            courses = ', '.join(g.course_name for g in f_grades[:3])
            flags.append(('Multiple F Grades', f'{len(f_grades)} failing: {courses}', 'danger'))
            severity = max(severity, 3)
        elif len(f_grades) == 1:
            flags.append(('Failing Course', f'F in {f_grades[0].course_name}', 'warning'))
            severity = max(severity, 2)

        if len(failing_courses) >= 3:
            flags.append(('Multiple D/F Grades', f'{len(failing_courses)} courses below C', 'danger'))
            severity = max(severity, 3)

        # GPA check
        gpa_grades = [g for g in recent_grades if g.gpa_points is not None]
        if gpa_grades:
            avg_gpa = sum(g.gpa_points for g in gpa_grades) / len(gpa_grades)
            if avg_gpa < 1.5:
                flags.append(('Very Low GPA', f'{avg_gpa:.2f} GPA', 'danger'))
                severity = max(severity, 3)
            elif avg_gpa < 2.0:
                flags.append(('Low GPA', f'{avg_gpa:.2f} GPA (below 2.0)', 'warning'))
                severity = max(severity, 2)

        # --- Transcript/graduation flags (from pre-fetched transcripts) ---
        latest_transcript = transcripts_by_student.get(s.id)
        if latest_transcript:
            if latest_transcript.risk_level == 'critical':
                flags.append(('Graduation Critical', f'{int(latest_transcript.total_completed)}/225 credits', 'danger'))
                severity = max(severity, 3)
            elif latest_transcript.risk_level == 'at-risk':
                flags.append(('Graduation At-Risk', f'{int(latest_transcript.total_completed)}/225 credits', 'warning'))
                severity = max(severity, 2)
            if latest_transcript.ag_status == 'deficient':
                flags.append(('a-g Deficient', f'{latest_transcript.ag_areas_met}/7 areas met', 'warning'))
                severity = max(severity, 2)

        # --- Counseling note flags (from pre-fetched counts) ---
        crisis_notes_30 = crisis_counts.get(s.id, 0)
        if crisis_notes_30 >= 2:
            flags.append(('Multiple Crisis Notes', f'{crisis_notes_30} crisis notes in 30 days', 'danger'))
            severity = max(severity, 3)
        elif crisis_notes_30 == 1:
            flags.append(('Recent Crisis Note', 'Crisis note in last 30 days', 'warning'))
            severity = max(severity, 2)

        # Overdue follow-ups
        overdue = overdue_counts.get(s.id, 0)
        if overdue >= 2:
            flags.append(('Overdue Follow-ups', f'{overdue} overdue follow-ups', 'warning'))
            severity = max(severity, 2)
        elif overdue == 1:
            flags.append(('Overdue Follow-up', '1 overdue follow-up', 'info'))
            severity = max(severity, 1)

        # No contact in 60+ days
        last_note_date = last_note_dates.get(s.id)
        last_svc_date = last_svc_dates.get(s.id)
        last_contact = last_note_date
        if last_svc_date and (not last_contact or last_svc_date > last_contact):
            last_contact = last_svc_date
        if last_contact and (today - last_contact).days > 60:
            days_since = (today - last_contact).days
            flags.append(('No Recent Contact', f'{days_since} days since last contact', 'info'))
            severity = max(severity, 1)

        if flags:
            flagged_students.append({
                'student': s,
                'flags': flags,
                'severity': severity,
                'severity_label': ['', 'Watch', 'Concern', 'Critical'][severity],
            })

    # Sort by severity (critical first)
    flagged_students.sort(key=lambda x: x['severity'], reverse=True)

    # Summary counts
    critical_count = sum(1 for f in flagged_students if f['severity'] == 3)
    concern_count = sum(1 for f in flagged_students if f['severity'] == 2)
    watch_count = sum(1 for f in flagged_students if f['severity'] == 1)

    log_action('view', 'report', details='Early Warning Report')

    return render_template('reports/early_warning.html',
        flagged_students=flagged_students,
        total_students=len(students),
        critical_count=critical_count,
        concern_count=concern_count,
        watch_count=watch_count)


# =====================================================================
#  COHORT TREND ANALYSIS
# =====================================================================

@reports_bp.route('/cohort-trends')
@login_required
def cohort_trends():
    """Cohort Trend Analysis — patterns across the caseload."""
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active').all()
    student_ids = [s.id for s in students]

    if not student_ids:
        return render_template('reports/cohort_trends.html',
            has_data=False, attendance_trends={}, grade_trends={},
            note_trends={}, grade_dist={}, risk_summary={})

    today = date.today()
    ninety_days_ago = today - timedelta(days=90)

    # --- Attendance trends by grade (single bulk query) ---
    # Map student_id → grade_level for bucketing
    grade_map = {s.id: (s.grade_level or 0) for s in students}

    all_att = AttendanceRecord.query.filter(
        AttendanceRecord.student_id.in_(student_ids),
        AttendanceRecord.date >= ninety_days_ago
    ).with_entities(
        AttendanceRecord.student_id, AttendanceRecord.status, AttendanceRecord.date
    ).all()

    attendance_by_grade = defaultdict(lambda: defaultdict(int))
    att_by_week = defaultdict(lambda: {'total': 0, 'absent': 0})

    for sid, status, att_date in all_att:
        grade = grade_map.get(sid, 0)
        attendance_by_grade[grade]['total'] += 1
        attendance_by_grade[grade][status] += 1

        week_start = att_date - timedelta(days=att_date.weekday())
        att_by_week[week_start.isoformat()]['total'] += 1
        if status == 'absent':
            att_by_week[week_start.isoformat()]['absent'] += 1

    att_rates_by_grade = {}
    for grade, data in sorted(attendance_by_grade.items()):
        if data['total'] > 0:
            att_rates_by_grade[grade] = round(data['present'] / data['total'] * 100, 1)

    att_weekly_rates = {}
    for week, data in sorted(att_by_week.items()):
        if data['total'] > 0:
            att_weekly_rates[week] = round((1 - data['absent'] / data['total']) * 100, 1)

    # --- Grade distribution by quarter ---
    # Scoped to ONE school year. Without this filter the buckets are keyed on
    # quarter alone, so a student's 9th-grade Q1 and 12th-grade Q1 merge into a
    # single "Q1" column — a *trend* report whose time axis flattens further
    # every year the caseload accumulates history. Also feeds grades_by_subject
    # below, so subject pass rates and GPA were lifetime averages too.
    trend_year = request.args.get('school_year') or current_school_year()
    grade_dist_by_quarter = defaultdict(lambda: defaultdict(int))
    all_grades = GradeRecord.query.filter(
        GradeRecord.student_id.in_(student_ids),
        GradeRecord.school_year == trend_year,
    ).all()
    for g in all_grades:
        q_label = f"Q{g.quarter}" if g.quarter else "Unknown"
        if g.letter_grade:
            # Bucket to letter (strip +/-)
            bucket = g.letter_grade[0] if g.letter_grade[0] in 'ABCDF' else g.letter_grade
            grade_dist_by_quarter[q_label][bucket] += 1

    # --- Grade trends by subject area ---
    grades_by_subject = defaultdict(lambda: {'total': 0, 'passing': 0, 'failing': 0, 'gpa_sum': 0.0, 'gpa_count': 0})
    for g in all_grades:
        subj = g.subject_area or 'Other'
        grades_by_subject[subj]['total'] += 1
        if g.is_passing:
            grades_by_subject[subj]['passing'] += 1
        elif g.is_passing is False:
            grades_by_subject[subj]['failing'] += 1
        if g.gpa_points is not None:
            grades_by_subject[subj]['gpa_sum'] += g.gpa_points
            grades_by_subject[subj]['gpa_count'] += 1

    subject_stats = {}
    for subj, data in sorted(grades_by_subject.items()):
        pass_rate = round(data['passing'] / data['total'] * 100, 1) if data['total'] > 0 else 0
        avg_gpa = round(data['gpa_sum'] / data['gpa_count'], 2) if data['gpa_count'] > 0 else None
        subject_stats[subj] = {
            'total': data['total'],
            'passing': data['passing'],
            'failing': data['failing'],
            'pass_rate': pass_rate,
            'avg_gpa': avg_gpa,
        }

    # --- Note/service trends by month ---
    note_by_month = defaultdict(lambda: defaultdict(int))
    recent_notes = Note.query.filter(
        Note.student_id.in_(student_ids),
        Note.session_date >= ninety_days_ago
    ).all()
    for n in recent_notes:
        month_key = n.session_date.strftime('%Y-%m')
        note_by_month[month_key][n.note_type] += 1

    # --- Transcript risk summary (single bulk query) ---
    risk_counts = defaultdict(int)
    ag_counts = defaultdict(int)
    all_transcripts = TranscriptRecord.query.filter(
        TranscriptRecord.student_id.in_(student_ids)
    ).order_by(TranscriptRecord.created_at.desc()).all()
    seen_transcript_sids = set()
    for tr in all_transcripts:
        if tr.student_id not in seen_transcript_sids:
            seen_transcript_sids.add(tr.student_id)
            risk_counts[tr.risk_level or 'unknown'] += 1
            ag_counts[tr.ag_status or 'unknown'] += 1

    has_data = bool(all_att or all_grades or recent_notes)

    log_action('view', 'report', details='Cohort Trends Report')

    return render_template('reports/cohort_trends.html',
        has_data=has_data,
        total_students=len(students),
        att_rates_by_grade=att_rates_by_grade,
        att_weekly_rates=att_weekly_rates,
        grade_dist_by_quarter=dict(grade_dist_by_quarter),
        subject_stats=subject_stats,
        note_by_month=dict(note_by_month),
        risk_counts=dict(risk_counts),
        ag_counts=dict(ag_counts))


# ── ASCA Results Reports ──────────────────────────────────────────

@reports_bp.route('/asca-results')
@login_required
def asca_results():
    """List of ASCA Results / Closing-the-Gap programs."""
    from app.models.asca_program import ASCAProgram
    program_type = request.args.get('type', '')
    query = ASCAProgram.query.filter_by(counselor_id=current_user.id)
    if program_type:
        query = query.filter_by(program_type=program_type)
    programs = query.order_by(ASCAProgram.created_at.desc()).all()
    log_action('view', 'report', details='ASCA Results Reports')
    return render_template('reports/asca_results.html',
        programs=programs, program_type=program_type,
        program_types=ASCAProgram.PROGRAM_TYPES)


@reports_bp.route('/asca-results/add', methods=['GET', 'POST'])
@login_required
def asca_results_add():
    from app.models.asca_program import ASCAProgram
    if request.method == 'POST':
        prog = ASCAProgram(
            counselor_id=current_user.id,
            name=request.form['name'].strip(),
            school_year=request.form.get('school_year', '').strip(),
            asca_domain=request.form.get('asca_domain', ''),
            program_type=request.form.get('program_type', 'results'),
            target_group=request.form.get('target_group', '').strip(),
            target_size=int(request.form['target_size']) if request.form.get('target_size') else None,
            goal_statement=request.form.get('goal_statement', '').strip(),
            asca_standard=request.form.get('asca_standard', '').strip(),
            baseline=request.form.get('baseline', '').strip(),
            intervention=request.form.get('intervention', '').strip(),
            process_data=request.form.get('process_data', '').strip(),
            perception_data=request.form.get('perception_data', '').strip(),
            results_data=request.form.get('results_data', '').strip(),
            outcome_data=request.form.get('outcome_data', '').strip(),
            implications=request.form.get('implications', '').strip(),
            start_date=parse_date(request.form.get('start_date')),
            end_date=parse_date(request.form.get('end_date')),
            status=request.form.get('status', 'active'),
        )
        db.session.add(prog)
        db.session.commit()
        log_action('create', 'asca_program', prog.id, f'Created ASCA program: {prog.name}')
        return redirect(url_for('reports.asca_results_view', id=prog.id))

    return render_template('reports/asca_results_form.html',
        program=None,
        program_types=ASCAProgram.PROGRAM_TYPES,
        statuses=ASCAProgram.STATUSES)


@reports_bp.route('/asca-results/<int:id>')
@login_required
def asca_results_view(id):
    from app.models.asca_program import ASCAProgram
    prog = owned_or_404(ASCAProgram, id)
    log_action('view', 'asca_program', prog.id)
    return render_template('reports/asca_results_view.html', program=prog)


@reports_bp.route('/asca-results/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def asca_results_edit(id):
    from app.models.asca_program import ASCAProgram
    prog = owned_or_404(ASCAProgram, id)
    if request.method == 'POST':
        prog.name = request.form['name'].strip()
        prog.school_year = request.form.get('school_year', '').strip()
        prog.asca_domain = request.form.get('asca_domain', '')
        prog.program_type = request.form.get('program_type', prog.program_type)
        prog.target_group = request.form.get('target_group', '').strip()
        prog.target_size = int(request.form['target_size']) if request.form.get('target_size') else None
        prog.goal_statement = request.form.get('goal_statement', '').strip()
        prog.asca_standard = request.form.get('asca_standard', '').strip()
        prog.baseline = request.form.get('baseline', '').strip()
        prog.intervention = request.form.get('intervention', '').strip()
        prog.process_data = request.form.get('process_data', '').strip()
        prog.perception_data = request.form.get('perception_data', '').strip()
        prog.results_data = request.form.get('results_data', '').strip()
        prog.outcome_data = request.form.get('outcome_data', '').strip()
        prog.implications = request.form.get('implications', '').strip()
        prog.start_date = parse_date(request.form.get('start_date'))
        prog.end_date = parse_date(request.form.get('end_date'))
        prog.status = request.form.get('status', prog.status)
        db.session.commit()
        log_action('update', 'asca_program', prog.id)
        return redirect(url_for('reports.asca_results_view', id=prog.id))

    return render_template('reports/asca_results_form.html',
        program=prog,
        program_types=ASCAProgram.PROGRAM_TYPES,
        statuses=ASCAProgram.STATUSES)


@reports_bp.route('/asca-results/<int:id>/delete', methods=['POST'])
@login_required
def asca_results_delete(id):
    from app.models.asca_program import ASCAProgram
    prog = owned_or_404(ASCAProgram, id)
    log_action('delete', 'asca_program', prog.id)
    db.session.delete(prog)
    db.session.commit()
    return redirect(url_for('reports.asca_results'))


@reports_bp.route('/closing-the-gap')
@login_required
def closing_the_gap():
    """Aggregate Closing-the-Gap data: services + activities by demographics."""
    student_ids_q = db.session.query(Student.id).filter_by(
        assigned_counselor_id=current_user.id
    )
    student_ids = [s[0] for s in student_ids_q.all()]

    # Service distribution by demographic dimensions
    students = Student.query.filter(Student.id.in_(student_ids)).all() if student_ids else []
    by_grade = defaultdict(lambda: {'students': 0, 'services': 0})
    by_ethnicity = defaultdict(lambda: {'students': 0, 'services': 0})
    by_el = defaultdict(lambda: {'students': 0, 'services': 0})
    by_iep = defaultdict(lambda: {'students': 0, 'services': 0})

    service_counts_per_student = dict(
        db.session.query(
            ServiceRecord.student_id,
            func.count(ServiceRecord.id)
        ).filter(ServiceRecord.student_id.in_(student_ids)).group_by(ServiceRecord.student_id).all()
    ) if student_ids else {}

    for s in students:
        sc = service_counts_per_student.get(s.id, 0)
        by_grade[s.grade_level or 0]['students'] += 1
        by_grade[s.grade_level or 0]['services'] += sc
        by_ethnicity[s.ethnicity or 'Unspecified']['students'] += 1
        by_ethnicity[s.ethnicity or 'Unspecified']['services'] += sc
        by_el[s.el_status or 'EO']['students'] += 1
        by_el[s.el_status or 'EO']['services'] += sc
        iep_label = 'IEP' if s.iep_status else ('504' if s.section_504 else 'No Plan')
        by_iep[iep_label]['students'] += 1
        by_iep[iep_label]['services'] += sc

    log_action('view', 'report', details='Closing-the-Gap Report')

    return render_template('reports/closing_the_gap.html',
        by_grade=dict(by_grade),
        by_ethnicity=dict(by_ethnicity),
        by_el=dict(by_el),
        by_iep=dict(by_iep),
        total_students=len(students))


@reports_bp.route('/equity')
@login_required
def equity():
    """Equity/access audit — disaggregated service delivery analysis."""
    from app.models.referral import Referral
    from app.models.goal import Goal
    from app.models.intervention import InterventionPlan

    students = Student.query.filter_by(assigned_counselor_id=current_user.id).all()
    sids = [s.id for s in students]

    if not sids:
        return render_template('reports/equity.html', has_data=False, sections=[])

    # Aggregate per dimension
    def by_dim(get_dim):
        buckets = defaultdict(lambda: {
            'students': 0, 'services': 0, 'notes': 0,
            'referrals': 0, 'goals': 0, 'interventions': 0,
        })
        # Index counts by student_id
        svc_counts = dict(db.session.query(ServiceRecord.student_id, func.count(ServiceRecord.id))
                          .filter(ServiceRecord.student_id.in_(sids))
                          .group_by(ServiceRecord.student_id).all())
        note_counts = dict(db.session.query(Note.student_id, func.count(Note.id))
                           .filter(Note.student_id.in_(sids))
                           .group_by(Note.student_id).all())
        ref_counts = dict(db.session.query(Referral.student_id, func.count(Referral.id))
                          .filter(Referral.student_id.in_(sids))
                          .group_by(Referral.student_id).all())
        goal_counts = dict(db.session.query(Goal.student_id, func.count(Goal.id))
                           .filter(Goal.student_id.in_(sids))
                           .group_by(Goal.student_id).all())
        int_counts = dict(db.session.query(InterventionPlan.student_id, func.count(InterventionPlan.id))
                          .filter(InterventionPlan.student_id.in_(sids))
                          .group_by(InterventionPlan.student_id).all())
        for s in students:
            key = get_dim(s)
            b = buckets[key]
            b['students'] += 1
            b['services'] += svc_counts.get(s.id, 0)
            b['notes'] += note_counts.get(s.id, 0)
            b['referrals'] += ref_counts.get(s.id, 0)
            b['goals'] += goal_counts.get(s.id, 0)
            b['interventions'] += int_counts.get(s.id, 0)
        return dict(buckets)

    sections = [
        ('Grade Level', by_dim(lambda s: f'Grade {s.grade_level}' if s.grade_level else 'Unspecified')),
        ('Ethnicity', by_dim(lambda s: s.ethnicity or 'Unspecified')),
        ('Gender', by_dim(lambda s: s.gender or 'Unspecified')),
        ('EL Status', by_dim(lambda s: s.el_status or 'EO')),
        ('Special Education', by_dim(lambda s: 'IEP' if s.iep_status else ('504' if s.section_504 else 'No Plan'))),
        ('AB Population', by_dim(lambda s: 'AB-Eligible' if s.has_ab_population else 'Not AB')),
    ]

    log_action('view', 'report', details='Equity / Access Audit')
    return render_template('reports/equity.html', sections=sections, has_data=True,
                           total_students=len(students))


@reports_bp.route('/program-evaluation')
@login_required
def program_evaluation():
    """Annual program evaluation: aggregate counts of services, groups, goals, referrals."""
    from app.models.goal import Goal
    from app.models.referral import Referral
    from app.models.group import CounselingGroup, GroupMember, GroupSession
    from app.models.communication import CommunicationLog

    school_year = request.args.get('school_year', '')
    # Default to current school year (Aug 1 - July 31)
    today = date.today()
    if today.month >= 8:
        year_start = date(today.year, 8, 1)
        year_end = date(today.year + 1, 7, 31)
    else:
        year_start = date(today.year - 1, 8, 1)
        year_end = date(today.year, 7, 31)

    sid_query = db.session.query(Student.id).filter_by(assigned_counselor_id=current_user.id)
    student_ids = [s[0] for s in sid_query.all()]

    counts = {
        'students': len(student_ids),
        'services': ServiceRecord.query.filter(
            ServiceRecord.counselor_id == current_user.id,
            ServiceRecord.date >= year_start, ServiceRecord.date <= year_end
        ).count(),
        'notes': Note.query.filter(
            Note.author_id == current_user.id,
            Note.session_date >= year_start, Note.session_date <= year_end
        ).count(),
        'goals_total': Goal.query.filter_by(counselor_id=current_user.id).count(),
        'goals_achieved': Goal.query.filter_by(counselor_id=current_user.id, status='achieved').count(),
        'referrals_total': Referral.query.filter_by(counselor_id=current_user.id).count(),
        'referrals_completed': Referral.query.filter_by(counselor_id=current_user.id, status='completed').count(),
        'groups_total': CounselingGroup.query.filter_by(counselor_id=current_user.id).count(),
        'groups_active': CounselingGroup.query.filter_by(counselor_id=current_user.id, status='active').count(),
        'group_sessions': db.session.query(GroupSession).join(CounselingGroup).filter(
            CounselingGroup.counselor_id == current_user.id
        ).count(),
        'group_members_total': db.session.query(GroupMember).join(CounselingGroup).filter(
            CounselingGroup.counselor_id == current_user.id
        ).count(),
        'communications': CommunicationLog.query.filter_by(counselor_id=current_user.id).count(),
    }

    log_action('view', 'report', details='Program Evaluation')

    return render_template('reports/program_evaluation.html',
        counts=counts, year_start=year_start, year_end=year_end)


# =====================================================================
# ELPAC Cohort Comparison Report
# =====================================================================

from app.models.elpac import ELPACScore  # noqa: E402
from app.routes.analytics import YEARS_BUCKETS, _years_in_us_schools_bucket  # noqa: E402
from collections import Counter  # noqa: E402, F811


_GROUP_BY_OPTIONS = [
    ('grade_level', 'Grade Level'),
    ('gender', 'Gender'),
    ('ethnicity', 'Ethnicity'),
    ('el_status', 'EL Status'),
    ('years_in_us_schools', 'Years in US Schools'),
    ('graduation_year', 'Graduation Cohort'),
    ('test_grade_level', 'Test Grade Level'),
]

_METRIC_OPTIONS = [
    ('overall_dist', 'Count at each Overall Level'),
    ('avg_overall_scale', 'Average Overall Scale Score'),
    ('avg_growth', 'Average Year-over-Year Growth'),
    ('rfep_rate', 'Reclassification Rate (% at Level 4)'),
    ('domain_profile', 'Domain Weakness Profile (avg L/S/R/W)'),
]


def _cohort_key(student, dim):
    if dim == 'grade_level':
        return str(student.grade_level) if student.grade_level else 'Unknown'
    if dim == 'gender':
        return student.gender or 'Unknown'
    if dim == 'ethnicity':
        return student.ethnicity or 'Unknown'
    if dim == 'el_status':
        return student.el_status or 'EO'
    if dim == 'years_in_us_schools':
        bucket = _years_in_us_schools_bucket(student)
        labels = {k: lbl for k, lbl, _, _ in YEARS_BUCKETS}
        return labels.get(bucket, 'Unknown')
    if dim == 'graduation_year':
        return f"Class of {student.graduation_year}" if student.graduation_year else 'Unknown'
    if dim == 'test_grade_level':
        latest = student.latest_elpac
        if latest and latest.test_grade_level:
            return f"Grade {latest.test_grade_level}"
        return 'Unknown'
    return 'Unknown'


def _compute_metric(students_in_cohort, metric):
    """Return a number (or dict for stacked metrics) for one cohort."""
    latests = [s.latest_elpac for s in students_in_cohort if s.latest_elpac]
    n = len(latests)

    if metric == 'overall_dist':
        # Stacked: return dict {1: count, 2: count, ...}
        dist = Counter()
        for lt in latests:
            if lt.overall_level:
                dist[lt.overall_level] += 1
        return {str(k): dist.get(k, 0) for k in (1, 2, 3, 4)}

    if metric == 'avg_overall_scale':
        scales = [lt.overall_scale for lt in latests if lt.overall_scale]
        return round(sum(scales) / len(scales)) if scales else 0

    if metric == 'avg_growth':
        growths = []
        for s in students_in_cohort:
            summatives = [r for r in s.elpac_scores if r.test_purpose == 'Summative']
            if len(summatives) >= 2 and summatives[0].overall_scale and summatives[1].overall_scale:
                growths.append(summatives[0].overall_scale - summatives[1].overall_scale)
        return round(sum(growths) / len(growths), 1) if growths else 0

    if metric == 'rfep_rate':
        if not latests:
            return 0
        l4 = sum(1 for lt in latests if lt.overall_level == 4)
        return round(100.0 * l4 / len(latests), 1)

    if metric == 'domain_profile':
        out = {}
        for dom in ('listening', 'speaking', 'reading', 'writing'):
            vals = [getattr(lt, f'{dom}_level') for lt in latests if getattr(lt, f'{dom}_level')]
            out[dom.capitalize()] = round(sum(vals) / len(vals), 2) if vals else 0
        return out

    return 0


# ── Cohort concentration in the master schedule ──────────────────

# Cohorts worth asking "are these students clustered?" about. Reuses
# _cohort_key so a cohort means the same thing here as in the ELPAC report,
# plus the boolean program flags that only make sense as a yes/no split.
_CONCENTRATION_COHORTS = [
    ('el_status', 'EL Status (Newcomer / LTEL / RFEP / EO)'),
    ('grade_level', 'Grade Level'),
    ('years_in_us_schools', 'Years in US Schools'),
    ('iep_status', 'IEP'),
    ('section_504', '504 Plan'),
    ('gender', 'Gender'),
    ('ethnicity', 'Ethnicity'),
]

_CONCENTRATION_DIMENSIONS = [
    ('period', 'Period'),
    ('teacher', 'Teacher'),
    ('course', 'Course'),
    ('advisory', 'Advisory Section'),
]

_TERM_OPTIONS = [('all', 'Any term'), ('Q1', 'Q1'), ('Q2', 'Q2'),
                 ('Q3', 'Q3'), ('Q4', 'Q4'), ('YR', 'Year-long')]


def _concentration_cohort_key(student, dim):
    """Cohort label, extending _cohort_key with the boolean program flags."""
    if dim == 'iep_status':
        return 'IEP' if student.iep_status else 'No IEP'
    if dim == 'section_504':
        return '504' if student.section_504 else 'No 504'
    return _cohort_key(student, dim)


@reports_bp.route('/cohort-concentration')
@login_required
def cohort_concentration():
    """Where a cohort sits in the master schedule."""
    from app.models.schedule import ScheduleEntry
    from app.utils.cohort_concentration import build_concentration, chart_payload

    cohort_dim = request.args.get('cohort', 'el_status')
    dimension = request.args.get('dimension', 'period')
    term = request.args.get('term', 'all')
    school_year = request.args.get('school_year') or current_school_year()

    if cohort_dim not in {k for k, _ in _CONCENTRATION_COHORTS}:
        cohort_dim = 'el_status'
    if dimension not in {k for k, _ in _CONCENTRATION_DIMENSIONS}:
        dimension = 'period'
    if term not in {k for k, _ in _TERM_OPTIONS}:
        term = 'all'

    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active').all()
    student_ids = [s.id for s in students]

    entries = []
    years = []
    if student_ids:
        years = sorted({y for (y,) in db.session.query(
            ScheduleEntry.school_year).filter(
                ScheduleEntry.student_id.in_(student_ids)).distinct().all() if y},
            reverse=True)
        if years and school_year not in years:
            school_year = years[0]
        entries = ScheduleEntry.query.filter(
            ScheduleEntry.student_id.in_(student_ids),
            ScheduleEntry.school_year == school_year,
        ).all()

    cohort_of = {s.id: _concentration_cohort_key(s, cohort_dim) for s in students}
    result = build_concentration(students, entries, cohort_of, dimension, term=term)

    log_action('view', 'report',
               details=f'Cohort concentration: {cohort_dim} by {dimension}')

    return render_template('reports/cohort_concentration.html',
        cohort_options=_CONCENTRATION_COHORTS,
        dimension_options=_CONCENTRATION_DIMENSIONS,
        term_options=_TERM_OPTIONS,
        cohort_dim=cohort_dim, dimension=dimension, term=term,
        school_year=school_year, years=years,
        result=result,
        chart=chart_payload(result),
        has_schedule_data=bool(entries),
    )


@reports_bp.route('/outcomes-by-section')
@login_required
def outcomes_by_section():
    """D/F rates for the counselor's own students, grouped by section."""
    from app.models.schedule import ScheduleEntry
    from app.utils.grade_outcomes import build_section_outcomes, chart_payload

    dimension = request.args.get('dimension', 'teacher')
    cohort_dim = request.args.get('cohort', 'el_status')
    cohort_filter = request.args.get('cohort_value', '')
    school_year = request.args.get('school_year') or current_school_year()

    if dimension not in {'teacher', 'period', 'course'}:
        dimension = 'teacher'
    if cohort_dim not in {k for k, _ in _CONCENTRATION_COHORTS}:
        cohort_dim = 'el_status'

    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active').all()
    student_ids = [s.id for s in students]

    entries, grades, years = [], [], []
    if student_ids:
        years = sorted({y for (y,) in db.session.query(
            ScheduleEntry.school_year).filter(
                ScheduleEntry.student_id.in_(student_ids)).distinct().all() if y},
            reverse=True)
        if years and school_year not in years:
            school_year = years[0]
        entries = ScheduleEntry.query.filter(
            ScheduleEntry.student_id.in_(student_ids),
            ScheduleEntry.school_year == school_year).all()
        grades = GradeRecord.query.filter(
            GradeRecord.student_id.in_(student_ids),
            GradeRecord.school_year == school_year).all()

    cohort_of = {s.id: _concentration_cohort_key(s, cohort_dim) for s in students}
    cohort_values = sorted(set(cohort_of.values()))
    if cohort_filter not in cohort_values:
        cohort_filter = ''

    result = build_section_outcomes(
        entries, grades, dimension=dimension,
        cohort_of=cohort_of, cohort_filter=cohort_filter or None)

    log_action('view', 'report',
               details=f'D/F outcomes by {dimension}'
                       + (f' for {cohort_filter}' if cohort_filter else ''))

    return render_template('reports/outcomes_by_section.html',
        dimension=dimension,
        dimension_options=[('teacher', 'Teacher'), ('period', 'Period'),
                           ('course', 'Course')],
        cohort_options=_CONCENTRATION_COHORTS,
        cohort_dim=cohort_dim, cohort_filter=cohort_filter,
        cohort_values=cohort_values,
        school_year=school_year, years=years,
        result=result, chart=chart_payload(result),
        has_data=bool(entries and grades))


@reports_bp.route('/elpac')
@login_required
def elpac_cohorts():
    """Cohort comparison report: group ELPAC results by demographics."""
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active').all()

    group_by = request.args.get('group_by', 'grade_level')
    metric = request.args.get('metric', 'overall_dist')
    el_filter = request.args.get('el_status_filter', 'all')

    if group_by not in {k for k, _ in _GROUP_BY_OPTIONS}:
        group_by = 'grade_level'
    if metric not in {k for k, _ in _METRIC_OPTIONS}:
        metric = 'overall_dist'

    if el_filter != 'all':
        students = [s for s in students if s.el_status == el_filter]

    # Group students into cohorts
    cohorts = defaultdict(list)
    for s in students:
        cohorts[_cohort_key(s, group_by)].append(s)

    # Compute metric per cohort
    cohort_data = []
    for label, members in sorted(cohorts.items()):
        cohort_data.append({
            'label': label,
            'count': len(members),
            'value': _compute_metric(members, metric),
        })

    log_action('view', 'report', details=f'ELPAC Cohorts: {group_by} / {metric}')

    return render_template('reports/elpac_cohorts.html',
        group_by_options=_GROUP_BY_OPTIONS,
        metric_options=_METRIC_OPTIONS,
        group_by=group_by,
        metric=metric,
        el_filter=el_filter,
        cohort_data=cohort_data,
        total_students=len(students),
    )


@reports_bp.route('/elpac/export.csv')
@login_required
def elpac_cohorts_export():
    """CSV export of the current cohort report."""
    import csv as _csv, io as _io
    from flask import Response

    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active').all()

    group_by = request.args.get('group_by', 'grade_level')
    metric = request.args.get('metric', 'overall_dist')
    el_filter = request.args.get('el_status_filter', 'all')

    if el_filter != 'all':
        students = [s for s in students if s.el_status == el_filter]

    cohorts = defaultdict(list)
    for s in students:
        cohorts[_cohort_key(s, group_by)].append(s)

    buf = _io.StringIO()
    writer = _csv.writer(buf)

    metric_label = dict(_METRIC_OPTIONS)[metric]
    group_label = dict(_GROUP_BY_OPTIONS)[group_by]

    if metric == 'overall_dist':
        writer.writerow([group_label, 'Count', 'Level 1', 'Level 2', 'Level 3', 'Level 4'])
        for label, members in sorted(cohorts.items()):
            v = _compute_metric(members, metric)
            writer.writerow([csv_safe(label), len(members), v.get('1', 0), v.get('2', 0), v.get('3', 0), v.get('4', 0)])
    elif metric == 'domain_profile':
        writer.writerow([group_label, 'Count', 'Listening', 'Speaking', 'Reading', 'Writing'])
        for label, members in sorted(cohorts.items()):
            v = _compute_metric(members, metric)
            writer.writerow([csv_safe(label), len(members), v.get('Listening', 0), v.get('Speaking', 0),
                             v.get('Reading', 0), v.get('Writing', 0)])
    else:
        writer.writerow([group_label, 'Count', metric_label])
        for label, members in sorted(cohorts.items()):
            writer.writerow([csv_safe(label), len(members), _compute_metric(members, metric)])

    return Response(buf.getvalue(), mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=ELPAC_Cohorts.csv'})
