"""Meeting Prep Packs — one-click student packet for SST/IEP/parent meetings."""
import json
from datetime import date, datetime, timedelta, timezone
from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from app.models.student import Student
from app.models.grade import GradeRecord
from app.models.note import Note
from app.models.attendance import AttendanceRecord
from app.models.iep504 import IEP504Record

meeting_prep_bp = Blueprint('meeting_prep', __name__)


def _attendance_summary(student_id, days=90):
    """Compute attendance stats for the last N days."""
    cutoff = date.today() - timedelta(days=days)
    records = AttendanceRecord.query.filter(
        AttendanceRecord.student_id == student_id,
        AttendanceRecord.date >= cutoff
    ).all()

    total = len(records)
    absent = sum(1 for r in records if r.status == 'absent')
    tardy = sum(1 for r in records if r.status == 'tardy')
    excused = sum(1 for r in records if r.status == 'excused')
    present = total - absent - tardy - excused

    rate = round(present / total * 100, 1) if total else None
    return {
        'total_records': total,
        'present': present,
        'absent': absent,
        'tardy': tardy,
        'excused': excused,
        'rate': rate,
        'days': days,
    }


def _gpa(student_id, school_year=None):
    """Compute unweighted GPA from grade records."""
    query = GradeRecord.query.filter_by(student_id=student_id)
    if school_year:
        query = query.filter_by(school_year=school_year)
    grades = query.all()

    points = [g.gpa_points for g in grades if g.gpa_points is not None]
    if not points:
        return None
    return round(sum(points) / len(points), 2)


def _current_grades(student_id):
    """Get the most recent quarter's grades for the student."""
    latest = (GradeRecord.query
              .filter_by(student_id=student_id)
              .order_by(GradeRecord.school_year.desc(),
                        GradeRecord.quarter.desc())
              .first())
    if not latest:
        return [], None, None

    grades = (GradeRecord.query
              .filter_by(student_id=student_id,
                         school_year=latest.school_year,
                         quarter=latest.quarter)
              .order_by(GradeRecord.period)
              .all())
    return grades, latest.school_year, latest.quarter


def _recent_notes(student_id, limit=10):
    """Get the most recent non-confidential notes."""
    return (Note.query
            .filter_by(student_id=student_id)
            .filter(Note.is_confidential == False)
            .order_by(Note.session_date.desc(), Note.created_at.desc())
            .limit(limit)
            .all())


def _active_followups(student_id):
    """Get open follow-ups for this student from JSON file."""
    import os
    data_dir = os.path.join(
        os.path.abspath(os.path.dirname(__file__)), '..', '..', 'data')
    followups_file = os.path.join(data_dir, 'followups.json')
    if not os.path.exists(followups_file):
        return []
    try:
        with open(followups_file, 'r') as f:
            all_fups = json.load(f)
    except (json.JSONDecodeError, IOError):
        return []

    student = Student.query.get(student_id)
    if not student:
        return []

    return [f for f in all_fups
            if f.get('counselor_id') == current_user.id
            and f.get('status') == 'open'
            and (f.get('student_id') == student.student_id_number
                 or f.get('student_name', '').lower() in (
                     student.full_name.lower(),
                     student.display_name.lower()))]


def _grad_snapshot(student):
    """Get graduation data using the graduation tracker's logic."""
    from app.routes.graduation import _build_student_grad_data
    return _build_student_grad_data(student)


def _build_prep_pack(student):
    """Assemble all data for a student's meeting prep pack."""
    grades, school_year, quarter = _current_grades(student.id)
    gpa = _gpa(student.id)
    gpa_current_year = _gpa(student.id, school_year) if school_year else None
    attendance = _attendance_summary(student.id)
    notes = _recent_notes(student.id)
    followups = _active_followups(student.id)
    grad = _grad_snapshot(student)
    iep504 = IEP504Record.query.filter_by(student_id=student.id).first()

    # Failing courses
    failing = [g for g in grades if not g.is_passing]

    return {
        'student': student,
        'grades': grades,
        'school_year': school_year,
        'quarter': quarter,
        'gpa': gpa,
        'gpa_current_year': gpa_current_year,
        'failing': failing,
        'attendance': attendance,
        'notes': notes,
        'followups': followups,
        'grad': grad,
        'iep504': iep504,
        'generated_at': datetime.now(timezone.utc),
    }


# ── Routes ────────────────────────────────────────────────────────

@meeting_prep_bp.route('/')
@login_required
def index():
    """Student selector for meeting prep packs."""
    students = (Student.query
                .filter_by(assigned_counselor_id=current_user.id,
                           status='active')
                .order_by(Student.last_name, Student.first_name)
                .all())
    return render_template('meeting_prep/index.html', students=students)


@meeting_prep_bp.route('/generate/<int:student_id>')
@login_required
def generate(student_id):
    """Generate a meeting prep pack for a specific student."""
    student = Student.query.filter_by(
        id=student_id,
        assigned_counselor_id=current_user.id
    ).first_or_404()

    meeting_type = request.args.get('type', 'general')
    pack = _build_prep_pack(student)
    pack['meeting_type'] = meeting_type

    return render_template('meeting_prep/pack.html', **pack)
