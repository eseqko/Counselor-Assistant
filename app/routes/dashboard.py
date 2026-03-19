from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app import db
from app.models.student import Student
from app.models.calendar_event import CalendarEvent
from app.models.note import Note
from app.models.activity import Activity
from app.models.service_record import ServiceRecord
from datetime import datetime, date, timedelta, timezone
import requests as http_requests
import re

dashboard_bp = Blueprint('dashboard', __name__)


def _fetch_todays_external_events(user):
    """Fetch today's events from the user's external iCal feed (Google Calendar, etc.)."""
    if not user.external_ical_url:
        return []
    try:
        resp = http_requests.get(user.external_ical_url, timeout=8)
        resp.raise_for_status()
    except Exception:
        return []

    today = date.today()
    events = []
    ics_text = re.sub(r'\r?\n[ \t]', '', resp.text)
    blocks = re.split(r'BEGIN:VEVENT', ics_text)

    for block in blocks[1:]:
        block = block.split('END:VEVENT')[0]
        props = {}
        for line in block.strip().splitlines():
            if ':' in line:
                key, _, value = line.partition(':')
                base_key = key.split(';')[0].strip()
                props[base_key] = value.strip()

        title = props.get('SUMMARY', '').replace('\\,', ',').replace('\\n', ' ')
        start_val = props.get('DTSTART', '')
        end_val = props.get('DTEND', '')
        location = props.get('LOCATION', '').replace('\\,', ',')

        if not start_val:
            continue

        # Parse the start datetime
        clean = start_val.replace('Z', '')
        start_dt = None
        is_all_day = False
        try:
            if len(clean) == 8:
                start_dt = datetime.strptime(clean, '%Y%m%d')
                is_all_day = True
            elif 'T' in clean:
                start_dt = datetime.strptime(clean, '%Y%m%dT%H%M%S')
        except ValueError:
            continue

        if not start_dt:
            continue

        # Check if event is today
        if start_dt.date() != today:
            # For all-day events, also check if today falls within the range
            if is_all_day and end_val:
                try:
                    end_dt = datetime.strptime(end_val.replace('Z', ''), '%Y%m%d')
                    if not (start_dt.date() <= today < end_dt.date()):
                        continue
                except ValueError:
                    continue
            else:
                continue

        # Parse end datetime
        end_dt = None
        if end_val:
            end_clean = end_val.replace('Z', '')
            try:
                if len(end_clean) == 8:
                    end_dt = datetime.strptime(end_clean, '%Y%m%d')
                elif 'T' in end_clean:
                    end_dt = datetime.strptime(end_clean, '%Y%m%dT%H%M%S')
            except ValueError:
                pass

        events.append({
            'title': title,
            'start_datetime': start_dt,
            'end_datetime': end_dt or (start_dt + timedelta(hours=1)),
            'location': location,
            'event_type': 'google_calendar',
            'status': 'scheduled',
            'is_external': True,
            'is_all_day': is_all_day,
        })

    events.sort(key=lambda e: e['start_datetime'])
    return events


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

    # Fetch external calendar events for today
    external_events = _fetch_todays_external_events(current_user)

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

    # Combined event count for stats card
    all_event_count = len(todays_events) + len(external_events)

    return render_template('dashboard/index.html',
        today=today,
        total_students=total_students,
        todays_events=todays_events,
        external_events=external_events,
        all_event_count=all_event_count,
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
