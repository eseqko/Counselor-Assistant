"""Smart alert engine — runs daily checks and generates action items.

Checks run once per day on first page load. Results are cached in the
AlertCache table so subsequent page loads are instant.
"""
import json
from datetime import datetime, date, timedelta, timezone
from sqlalchemy.orm import joinedload
from app import db
from app.models.student import Student
from app.models.note import Note
from app.models.iep504 import IEP504Record
from app.models.grade import GradeRecord
from app.models.attendance import AttendanceRecord
from app.models.availability import Booking
from app.models.calendar_event import CalendarEvent


class AlertCache(db.Model):
    """One row per counselor per day — caches computed alerts as JSON."""
    __tablename__ = 'alert_cache'

    id = db.Column(db.Integer, primary_key=True)
    counselor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    cache_date = db.Column(db.Date, nullable=False)
    alerts_json = db.Column(db.Text, nullable=False, default='[]')
    generated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('counselor_id', 'cache_date', name='uq_alert_cache_day'),
    )


# ── Alert categories & priorities ─────────────────────────────────

PRIORITY_CRITICAL = 1
PRIORITY_HIGH = 2
PRIORITY_MEDIUM = 3
PRIORITY_LOW = 4

PRIORITY_LABELS = {
    PRIORITY_CRITICAL: 'critical',
    PRIORITY_HIGH: 'high',
    PRIORITY_MEDIUM: 'medium',
    PRIORITY_LOW: 'low',
}

CATEGORY_COMPLIANCE = 'compliance'
CATEGORY_ACADEMIC = 'academic'
CATEGORY_ATTENDANCE = 'attendance'
CATEGORY_FOLLOWUP = 'follow-up'
CATEGORY_STUDENT = 'student'
CATEGORY_SCHEDULING = 'scheduling'
CATEGORY_WORKFLOW = 'workflow'


# ── Public API ────────────────────────────────────────────────────

def get_alerts(user):
    """Return cached alerts for today, generating if needed."""
    today = date.today()
    cache = AlertCache.query.filter_by(
        counselor_id=user.id, cache_date=today
    ).first()

    if cache:
        return json.loads(cache.alerts_json)

    # Generate fresh alerts
    alerts = _generate_alerts(user)

    # Store in cache
    cache = AlertCache(
        counselor_id=user.id,
        cache_date=today,
        alerts_json=json.dumps(alerts, default=str),
    )
    db.session.add(cache)

    # Clean old cache entries (keep last 7 days)
    cutoff = today - timedelta(days=7)
    AlertCache.query.filter(
        AlertCache.counselor_id == user.id,
        AlertCache.cache_date < cutoff,
    ).delete()

    db.session.commit()
    return alerts


def refresh_alerts(user):
    """Force-regenerate alerts (e.g., after data changes)."""
    today = date.today()
    AlertCache.query.filter_by(
        counselor_id=user.id, cache_date=today
    ).delete()
    db.session.commit()
    return get_alerts(user)


def get_alert_count(user):
    """Quick count for the notification badge — no generation if no cache."""
    today = date.today()
    cache = AlertCache.query.filter_by(
        counselor_id=user.id, cache_date=today
    ).first()
    if not cache:
        # Generate on first access
        alerts = get_alerts(user)
        return len(alerts)
    alerts = json.loads(cache.alerts_json)
    return len(alerts)


# ── Alert generation ──────────────────────────────────────────────

def _generate_alerts(user):
    """Run all alert checks and return sorted list of alerts."""
    alerts = []
    today = date.today()

    # Load counselor's active students once
    students = Student.query.filter_by(
        assigned_counselor_id=user.id, status='active'
    ).all()
    student_ids = [s.id for s in students]
    student_map = {s.id: s for s in students}

    if student_ids:
        alerts += _check_iep504_reviews(user, student_ids, student_map, today)
        alerts += _check_overdue_followups(user, today)
        alerts += _check_no_contact_students(user, students, today)
        alerts += _check_failing_grades(user, student_ids, student_map)
        alerts += _check_attendance_alerts(user, student_ids, student_map, today)

    alerts += _check_upcoming_bookings(user, today)
    alerts += _check_post_meeting_followups(user, today)
    alerts += _check_semester_tasks(user, today)
    alerts += _check_new_students(user, students, today)

    # Sort by priority, then category
    alerts.sort(key=lambda a: (a['priority'], a['category']))

    return alerts


def _alert(priority, category, title, detail='', student_id=None,
           student_name='', action_url='', action_label=''):
    return {
        'priority': priority,
        'priority_label': PRIORITY_LABELS.get(priority, 'low'),
        'category': category,
        'title': title,
        'detail': detail,
        'student_id': student_id,
        'student_name': student_name,
        'action_url': action_url,
        'action_label': action_label,
    }


# ── Individual checks ─────────────────────────────────────────────

def _check_iep504_reviews(user, student_ids, student_map, today):
    """IEP/504 reviews due within 30 days or overdue."""
    alerts = []
    records = IEP504Record.query.filter(
        IEP504Record.student_id.in_(student_ids),
        IEP504Record.next_review_date.isnot(None),
    ).all()

    for rec in records:
        student = student_map.get(rec.student_id)
        if not student:
            continue
        name = student.first_name + ' ' + student.last_name
        days_until = (rec.next_review_date - today).days

        if days_until < 0:
            alerts.append(_alert(
                PRIORITY_CRITICAL, CATEGORY_COMPLIANCE,
                f'{rec.plan_type.upper()} review OVERDUE',
                f'{name} — was due {abs(days_until)} days ago ({rec.next_review_date.strftime("%m/%d")})',
                student_id=rec.student_id, student_name=name,
                action_url=f'/iep504', action_label='View IEP/504',
            ))
        elif days_until <= 14:
            alerts.append(_alert(
                PRIORITY_HIGH, CATEGORY_COMPLIANCE,
                f'{rec.plan_type.upper()} review in {days_until} days',
                f'{name} — due {rec.next_review_date.strftime("%m/%d/%Y")}',
                student_id=rec.student_id, student_name=name,
                action_url=f'/iep504', action_label='View IEP/504',
            ))
        elif days_until <= 30:
            alerts.append(_alert(
                PRIORITY_MEDIUM, CATEGORY_COMPLIANCE,
                f'{rec.plan_type.upper()} review in {days_until} days',
                f'{name} — due {rec.next_review_date.strftime("%m/%d/%Y")}',
                student_id=rec.student_id, student_name=name,
                action_url=f'/iep504', action_label='View IEP/504',
            ))

    return alerts


def _check_overdue_followups(user, today):
    """Follow-up tasks that are overdue."""
    alerts = []
    overdue_notes = Note.query.options(joinedload(Note.student)).filter(
        Note.author_id == user.id,
        Note.follow_up_needed == True,
        Note.follow_up_date < today,
        db.or_(Note.follow_up_completed == False, Note.follow_up_completed.is_(None)),
    ).all()

    for note in overdue_notes:
        student = note.student
        if not student:
            continue
        name = student.first_name + ' ' + student.last_name
        days_overdue = (today - note.follow_up_date).days
        alerts.append(_alert(
            PRIORITY_HIGH if days_overdue > 3 else PRIORITY_MEDIUM,
            CATEGORY_FOLLOWUP,
            f'Follow-up overdue ({days_overdue}d)',
            f'{name} — {note.title or note.note_type}',
            student_id=student.id, student_name=name,
            action_url=f'/notes/{note.id}', action_label='View Note',
        ))

    return alerts


def _check_no_contact_students(user, students, today):
    """Students not contacted in 30+ days."""
    alerts = []
    threshold = today - timedelta(days=30)
    student_ids = [s.id for s in students]

    # Single bulk query: last note date per student
    last_contact = dict(
        db.session.query(
            Note.student_id,
            db.func.max(Note.session_date)
        ).filter(
            Note.author_id == user.id,
            Note.student_id.in_(student_ids),
        ).group_by(Note.student_id).all()
    )

    for student in students:
        last_date = last_contact.get(student.id)
        if last_date and last_date >= threshold:
            continue

        name = student.first_name + ' ' + student.last_name
        if last_date:
            days_since = (today - last_date).days
            detail = f'Last contact: {days_since} days ago ({last_date.strftime("%m/%d")})'
        else:
            detail = 'No counseling notes on record'

        alerts.append(_alert(
            PRIORITY_LOW, CATEGORY_STUDENT,
            f'Check-in needed: {name}',
            detail,
            student_id=student.id, student_name=name,
            action_url=f'/notes/add?student_id={student.id}', action_label='Add Note',
        ))

    return alerts


def _check_failing_grades(user, student_ids, student_map):
    """Students with D or F grades in current grading period."""
    alerts = []
    # Get the most recent grades per student
    failing_grades = GradeRecord.query.filter(
        GradeRecord.student_id.in_(student_ids),
        GradeRecord.letter_grade.in_(['F', 'D', 'D-', 'D+']),
    ).order_by(GradeRecord.school_year.desc(), GradeRecord.quarter.desc()).all()

    # Group by student — only flag each student once with their failing courses
    student_fails = {}
    for g in failing_grades:
        if g.student_id not in student_fails:
            student_fails[g.student_id] = []
        if len(student_fails[g.student_id]) < 5:  # cap at 5 courses
            student_fails[g.student_id].append(
                f'{g.course_name} ({g.letter_grade})'
            )

    for sid, courses in student_fails.items():
        student = student_map.get(sid)
        if not student:
            continue
        name = student.first_name + ' ' + student.last_name
        count = len(courses)
        priority = PRIORITY_HIGH if count >= 3 else PRIORITY_MEDIUM

        alerts.append(_alert(
            priority, CATEGORY_ACADEMIC,
            f'{count} failing/near-failing grade{"s" if count > 1 else ""}',
            f'{name} — {", ".join(courses[:3])}{"..." if count > 3 else ""}',
            student_id=sid, student_name=name,
            action_url=f'/caseload/{sid}', action_label='View Student',
        ))

    return alerts


def _check_attendance_alerts(user, student_ids, student_map, today):
    """Students with high absence rates in the last 30 days."""
    alerts = []
    cutoff = today - timedelta(days=30)

    # Single bulk query: absence count per student
    absence_counts = dict(
        db.session.query(
            AttendanceRecord.student_id,
            db.func.count(AttendanceRecord.id)
        ).filter(
            AttendanceRecord.student_id.in_(student_ids),
            AttendanceRecord.date >= cutoff,
            AttendanceRecord.status == 'absent',
            AttendanceRecord.period == 0,
        ).group_by(AttendanceRecord.student_id).all()
    )

    for sid, absent_count in absence_counts.items():
        if absent_count < 3:
            continue

        student = student_map.get(sid)
        if not student:
            continue
        name = student.first_name + ' ' + student.last_name

        if absent_count >= 7:
            priority = PRIORITY_HIGH
            label = 'Chronic absence alert'
        elif absent_count >= 5:
            priority = PRIORITY_MEDIUM
            label = 'Attendance concern'
        else:
            priority = PRIORITY_LOW
            label = 'Attendance watch'

        alerts.append(_alert(
            priority, CATEGORY_ATTENDANCE,
            f'{label}: {absent_count} absences (30 days)',
            f'{name}',
            student_id=sid, student_name=name,
            action_url=f'/caseload/{sid}', action_label='View Student',
        ))

    return alerts


def _check_upcoming_bookings(user, today):
    """Bookings happening today or tomorrow — prep reminder."""
    alerts = []
    tomorrow = today + timedelta(days=1)

    bookings = Booking.query.filter(
        Booking.counselor_id == user.id,
        Booking.appointment_date.in_([today, tomorrow]),
        Booking.status == 'confirmed',
    ).order_by(Booking.appointment_date, Booking.start_time).all()

    for b in bookings:
        is_today = b.appointment_date == today
        time_label = f'{"Today" if is_today else "Tomorrow"} at {b.start_time}'
        meeting_label = dict(Booking.MEETING_TYPES).get(b.meeting_type, b.meeting_type)

        alerts.append(_alert(
            PRIORITY_HIGH if is_today else PRIORITY_MEDIUM,
            CATEGORY_SCHEDULING,
            f'Booking: {b.booker_name}',
            f'{time_label} — {meeting_label}'
            + (f' (Student: {b.student_name})' if b.student_name else ''),
            action_url='/scheduling', action_label='View Bookings',
        ))

    return alerts


def _check_post_meeting_followups(user, today):
    """Events from yesterday that might need follow-up notes."""
    alerts = []
    yesterday = today - timedelta(days=1)

    events = CalendarEvent.query.filter(
        CalendarEvent.owner_id == user.id,
        db.func.date(CalendarEvent.start_datetime) == yesterday,
        CalendarEvent.event_type.in_([
            'parent_conference', 'meeting', 'group_session',
        ]),
        CalendarEvent.status != 'cancelled',
    ).all()

    if not events:
        return alerts

    # Single check: any note written for yesterday?
    has_note = Note.query.filter(
        Note.author_id == user.id,
        Note.session_date == yesterday,
    ).first()

    if not has_note:
        for event in events:
            alerts.append(_alert(
                PRIORITY_LOW, CATEGORY_WORKFLOW,
                f'Follow-up needed from yesterday',
                f'"{event.title}" — consider writing a counseling note',
                action_url='/notes/add', action_label='Add Note',
            ))

    return alerts


def _check_semester_tasks(user, today):
    """Beginning/end of semester checklist reminders."""
    alerts = []
    month = today.month
    day = today.day

    # August (back to school)
    if month == 8 and 1 <= day <= 20:
        alerts.append(_alert(
            PRIORITY_MEDIUM, CATEGORY_WORKFLOW,
            'Start-of-year tasks',
            'Review caseload rosters, schedule new student intakes, '
            'verify IEP/504 records are current',
            action_url='/caseload', action_label='Caseload',
        ))

    # January (spring semester start)
    if month == 1 and 2 <= day <= 15:
        alerts.append(_alert(
            PRIORITY_MEDIUM, CATEGORY_WORKFLOW,
            'Spring semester prep',
            'Review schedule change requests, update graduation audits, '
            'check mid-year IEP/504 reviews',
            action_url='/graduation', action_label='Grad Tracker',
        ))

    # May (end of year)
    if month == 5 and 1 <= day <= 20:
        alerts.append(_alert(
            PRIORITY_MEDIUM, CATEGORY_WORKFLOW,
            'End-of-year tasks',
            'Finalize transcripts, complete senior clearance, '
            'archive counseling notes, run annual reports',
            action_url='/reports', action_label='Reports',
        ))

    # November/March — FAFSA season reminders for seniors
    if month in (10, 11, 12, 1, 2, 3):
        senior_count = Student.query.filter_by(
            assigned_counselor_id=user.id, status='active', grade_level=12
        ).count()
        if senior_count > 0 and day <= 5:
            alerts.append(_alert(
                PRIORITY_LOW, CATEGORY_WORKFLOW,
                f'FAFSA check-in ({senior_count} seniors)',
                'Monthly reminder to check on FAFSA completion status',
                action_url='/email-drafts', action_label='Comm Drafts',
            ))

    return alerts


def _check_new_students(user, students, today):
    """Recently added students that might need welcome workflow."""
    alerts = []
    recent_cutoff = today - timedelta(days=7)

    # Filter to recent students first
    recent = [s for s in students
              if s.enrollment_date and s.enrollment_date >= recent_cutoff]
    if not recent:
        return alerts

    # Bulk check which of these have notes
    recent_ids = [s.id for s in recent]
    has_notes = set(
        sid for (sid,) in db.session.query(Note.student_id).filter(
            Note.author_id == user.id,
            Note.student_id.in_(recent_ids),
        ).distinct().all()
    )

    for student in recent:
        if student.id in has_notes:
            continue
        name = student.first_name + ' ' + student.last_name
        days_since = (today - student.enrollment_date).days
        alerts.append(_alert(
            PRIORITY_MEDIUM, CATEGORY_STUDENT,
            f'New student: {name}',
            f'Added {days_since} day{"s" if days_since != 1 else ""} ago — '
            f'schedule intro meeting and review records',
            student_id=student.id, student_name=name,
            action_url=f'/notes/add?student_id={student.id}',
            action_label='Add Note',
        ))

    return alerts
