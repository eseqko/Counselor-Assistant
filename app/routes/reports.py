from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from app import db
from app.models.activity import Activity
from app.models.note import Note
from app.models.service_record import ServiceRecord
from app.models.student import Student
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
