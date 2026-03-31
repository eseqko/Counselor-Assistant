"""Data Visualizations — analytics dashboard with Chart.js."""
from datetime import date, timedelta, timezone
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.student import Student
from app.models.grade import GradeRecord
from app.models.attendance import AttendanceRecord
from app.models.note import Note
from app.models.service_record import ServiceRecord
from app.models.activity import Activity
from app.models.iep504 import IEP504Record
from sqlalchemy import func

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


# ── Data aggregation functions ────────────────────────────────────

def _caseload_data(students):
    """Grade level distribution and demographics."""
    grade_dist = {}
    iep_count = 0
    s504_count = 0
    el_count = 0
    total = len(students)

    for s in students:
        gl = s.grade_level or 0
        grade_dist[gl] = grade_dist.get(gl, 0) + 1
        if s.iep_status:
            iep_count += 1
        if s.section_504:
            s504_count += 1
        if s.el_status and s.el_status in ('Newcomer', 'LTEL', 'EL 1', 'EL 2', 'EL 3'):
            el_count += 1

    gen_ed = total - iep_count - s504_count - el_count

    return {
        'total': total,
        'grade_distribution': {
            'labels': [f'Grade {g}' for g in sorted(grade_dist.keys())],
            'values': [grade_dist[g] for g in sorted(grade_dist.keys())],
        },
        'demographics': {
            'labels': ['IEP', '504 Plan', 'English Learner', 'Gen Ed'],
            'values': [iep_count, s504_count, el_count, max(0, gen_ed)],
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

    # Combine and sort by total count descending, take top 8
    all_subjects = set(list(failing_f.keys()) + list(failing_d.keys()))
    combined = [(s, failing_f.get(s, 0) + failing_d.get(s, 0)) for s in all_subjects]
    sorted_failing = sorted(combined, key=lambda x: -x[1])[:8]
    top_subjects = [f[0] for f in sorted_failing]

    return {
        'gpa_distribution': {
            'labels': list(gpa_buckets.keys()),
            'values': list(gpa_buckets.values()),
        },
        'failing_by_subject': {
            'labels': top_subjects,
            'f_values': [failing_f.get(s, 0) for s in top_subjects],
            'd_values': [failing_d.get(s, 0) for s in top_subjects],
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
        AttendanceRecord.period == 0,
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
