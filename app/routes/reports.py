import json
from flask import Blueprint, render_template, request
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
from app.utils.helpers import parse_date
from datetime import date, timedelta
from collections import defaultdict

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
        selected_student = Student.query.get(int(student_id))
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
    sixty_days_ago = today - timedelta(days=60)
    ninety_days_ago = today - timedelta(days=90)

    flagged_students = []

    for s in students:
        flags = []
        severity = 0  # 0=none, 1=watch, 2=concern, 3=critical

        # --- Attendance flags ---
        absences_30 = AttendanceRecord.query.filter(
            AttendanceRecord.student_id == s.id,
            AttendanceRecord.date >= thirty_days_ago,
            AttendanceRecord.status == 'absent'
        ).count()
        tardies_30 = AttendanceRecord.query.filter(
            AttendanceRecord.student_id == s.id,
            AttendanceRecord.date >= thirty_days_ago,
            AttendanceRecord.status == 'tardy'
        ).count()
        total_att_30 = AttendanceRecord.query.filter(
            AttendanceRecord.student_id == s.id,
            AttendanceRecord.date >= thirty_days_ago
        ).count()

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
            present_30 = AttendanceRecord.query.filter(
                AttendanceRecord.student_id == s.id,
                AttendanceRecord.date >= thirty_days_ago,
                AttendanceRecord.status == 'present'
            ).count()
            att_rate = round(present_30 / total_att_30 * 100, 1)
            if att_rate < 90:
                flags.append(('Low Attendance Rate', f'{att_rate}% (below 90% threshold)', 'danger'))
                severity = max(severity, 3)

        # --- Grade flags ---
        recent_grades = GradeRecord.query.filter(
            GradeRecord.student_id == s.id
        ).order_by(GradeRecord.school_year.desc(), GradeRecord.quarter.desc()).limit(8).all()

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

        # --- Transcript/graduation flags ---
        latest_transcript = s.transcript_records.first()
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

        # --- Counseling note flags ---
        crisis_notes_30 = Note.query.filter(
            Note.student_id == s.id,
            Note.note_type == 'crisis',
            Note.session_date >= thirty_days_ago
        ).count()
        if crisis_notes_30 >= 2:
            flags.append(('Multiple Crisis Notes', f'{crisis_notes_30} crisis notes in 30 days', 'danger'))
            severity = max(severity, 3)
        elif crisis_notes_30 == 1:
            flags.append(('Recent Crisis Note', 'Crisis note in last 30 days', 'warning'))
            severity = max(severity, 2)

        # Overdue follow-ups
        overdue = Note.query.filter(
            Note.student_id == s.id,
            Note.follow_up_needed == True,
            Note.follow_up_date < today
        ).count()
        if overdue >= 2:
            flags.append(('Overdue Follow-ups', f'{overdue} overdue follow-ups', 'warning'))
            severity = max(severity, 2)
        elif overdue == 1:
            flags.append(('Overdue Follow-up', '1 overdue follow-up', 'info'))
            severity = max(severity, 1)

        # No contact in 60+ days
        last_note = Note.query.filter_by(student_id=s.id).order_by(
            Note.session_date.desc()).first()
        last_service = ServiceRecord.query.filter_by(student_id=s.id).order_by(
            ServiceRecord.date.desc()).first()
        last_contact = None
        if last_note and last_note.session_date:
            last_contact = last_note.session_date
        if last_service and last_service.date:
            if not last_contact or last_service.date > last_contact:
                last_contact = last_service.date
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

    # --- Attendance trends by grade ---
    attendance_by_grade = defaultdict(lambda: {'total': 0, 'absent': 0, 'tardy': 0, 'present': 0})
    for s in students:
        grade = s.grade_level or 0
        records = AttendanceRecord.query.filter(
            AttendanceRecord.student_id == s.id,
            AttendanceRecord.date >= ninety_days_ago
        ).all()
        for r in records:
            attendance_by_grade[grade]['total'] += 1
            attendance_by_grade[grade][r.status] += 1

    # Attendance rate by grade
    att_rates_by_grade = {}
    for grade, data in sorted(attendance_by_grade.items()):
        if data['total'] > 0:
            att_rates_by_grade[grade] = round(data['present'] / data['total'] * 100, 1)

    # --- Attendance trend by week ---
    att_by_week = defaultdict(lambda: {'total': 0, 'absent': 0})
    all_att = AttendanceRecord.query.filter(
        AttendanceRecord.student_id.in_(student_ids),
        AttendanceRecord.date >= ninety_days_ago
    ).all()
    for r in all_att:
        week_start = r.date - timedelta(days=r.date.weekday())
        att_by_week[week_start.isoformat()]['total'] += 1
        if r.status == 'absent':
            att_by_week[week_start.isoformat()]['absent'] += 1

    att_weekly_rates = {}
    for week, data in sorted(att_by_week.items()):
        if data['total'] > 0:
            att_weekly_rates[week] = round((1 - data['absent'] / data['total']) * 100, 1)

    # --- Grade distribution by quarter ---
    grade_dist_by_quarter = defaultdict(lambda: defaultdict(int))
    all_grades = GradeRecord.query.filter(
        GradeRecord.student_id.in_(student_ids)
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

    # --- Transcript risk summary ---
    risk_counts = defaultdict(int)
    ag_counts = defaultdict(int)
    for s in students:
        tr = s.transcript_records.first()
        if tr:
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
