from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app import db
from app.models.student import Student
from app.models.calendar_event import CalendarEvent
from app.models.note import Note
from app.models.activity import Activity
from app.models.service_record import ServiceRecord
from datetime import datetime, date, timedelta, timezone

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@login_required
def index():
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    # Stats
    total_students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active').count()
    todays_events = CalendarEvent.query.filter(
        CalendarEvent.owner_id == current_user.id,
        db.func.date(CalendarEvent.start_datetime) == today
    ).order_by(CalendarEvent.start_datetime).all()

    recent_notes = Note.query.filter_by(author_id=current_user.id).order_by(
        Note.created_at.desc()).limit(5).all()

    # Weekly activity summary
    week_activities = Activity.query.filter(
        Activity.counselor_id == current_user.id,
        Activity.date >= week_start,
        Activity.date <= week_end
    ).all()

    total_minutes = sum(a.duration_minutes or 0 for a in week_activities)
    direct_minutes = sum(a.duration_minutes or 0 for a in week_activities
                        if a.service_type == 'direct_student')
    indirect_minutes = sum(a.duration_minutes or 0 for a in week_activities
                          if a.service_type == 'indirect_student')
    mgmt_minutes = sum(a.duration_minutes or 0 for a in week_activities
                       if a.service_type == 'program_management')
    non_minutes = sum(a.duration_minutes or 0 for a in week_activities
                      if a.service_type == 'non_counseling')

    # Follow-ups due
    follow_ups = Note.query.filter(
        Note.author_id == current_user.id,
        Note.follow_up_needed == True,
        Note.follow_up_date <= today + timedelta(days=7)
    ).order_by(Note.follow_up_date).limit(10).all()

    # Recent service records
    recent_services = ServiceRecord.query.filter_by(
        counselor_id=current_user.id
    ).order_by(ServiceRecord.date.desc()).limit(5).all()

    return render_template('dashboard/index.html',
        today=today,
        total_students=total_students,
        todays_events=todays_events,
        recent_notes=recent_notes,
        recent_services=recent_services,
        follow_ups=follow_ups,
        total_minutes=total_minutes,
        direct_minutes=direct_minutes,
        indirect_minutes=indirect_minutes,
        mgmt_minutes=mgmt_minutes,
        non_minutes=non_minutes,
        week_activities=week_activities,
    )
