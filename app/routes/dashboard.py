from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from app import db
from app.models.student import Student
from app.models.calendar_event import CalendarEvent
from app.models.note import Note
from app.models.activity import Activity
from app.models.service_record import ServiceRecord
from datetime import datetime, date, timedelta, timezone
import requests as http_requests
import pytz
import re

dashboard_bp = Blueprint('dashboard', __name__)


def _extract_ical_timezone(ics_text):
    """Extract the calendar-level timezone from X-WR-TIMEZONE or first VTIMEZONE."""
    m = re.search(r'X-WR-TIMEZONE:(.*)', ics_text)
    if m:
        return m.group(1).strip()
    m = re.search(r'BEGIN:VTIMEZONE.*?TZID:(.*?)[\r\n]', ics_text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return None


def _parse_ical_dt_with_tz(raw_value, full_key, cal_tz):
    """Parse an iCal datetime and convert to the calendar's local timezone.

    Returns (naive_local_datetime, is_all_day).
    - TZID on property: time is already in that timezone, convert to cal_tz
    - Z suffix: time is UTC, convert to cal_tz
    - VALUE=DATE: all-day event, return date-only
    - No timezone info: floating time, assume already local
    """
    if not raw_value:
        return None, False

    clean = raw_value.replace('Z', '')

    # All-day event
    if 'VALUE=DATE' in full_key or (len(clean) == 8 and 'T' not in clean):
        try:
            return datetime.strptime(clean[:8], '%Y%m%d'), True
        except ValueError:
            return None, False

    # Parse the naive datetime
    try:
        naive = datetime.strptime(clean, '%Y%m%dT%H%M%S')
    except ValueError:
        return None, False

    target_tz = None
    if cal_tz:
        try:
            target_tz = pytz.timezone(cal_tz)
        except pytz.exceptions.UnknownTimeZoneError:
            pass

    # Check for TZID on this specific property
    tzid_match = re.search(r'TZID=([^;:]+)', full_key)
    if tzid_match:
        prop_tz_name = tzid_match.group(1)
        try:
            prop_tz = pytz.timezone(prop_tz_name)
            aware = prop_tz.localize(naive)
            if target_tz and prop_tz_name != cal_tz:
                aware = aware.astimezone(target_tz)
            return aware.replace(tzinfo=None), False
        except (pytz.exceptions.UnknownTimeZoneError, Exception):
            return naive, False

    # UTC (Z suffix)
    if raw_value.endswith('Z'):
        utc_dt = pytz.utc.localize(naive)
        if target_tz:
            local_dt = utc_dt.astimezone(target_tz)
            return local_dt.replace(tzinfo=None), False
        return naive, False

    # Floating time — already local
    return naive, False


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
    cal_tz = _extract_ical_timezone(ics_text)
    blocks = re.split(r'BEGIN:VEVENT', ics_text)

    for block in blocks[1:]:
        block = block.split('END:VEVENT')[0]
        props = {}
        full_keys = {}
        for line in block.strip().splitlines():
            if ':' in line:
                key, _, value = line.partition(':')
                base_key = key.split(';')[0].strip()
                props[base_key] = value.strip()
                full_keys[base_key] = key.strip()

        title = props.get('SUMMARY', '').replace('\\,', ',').replace('\\n', ' ')
        start_val = props.get('DTSTART', '')
        end_val = props.get('DTEND', '')
        location = props.get('LOCATION', '').replace('\\,', ',')

        if not start_val:
            continue

        start_key = full_keys.get('DTSTART', '')
        end_key = full_keys.get('DTEND', '')

        start_dt, is_all_day = _parse_ical_dt_with_tz(start_val, start_key, cal_tz)
        if not start_dt:
            continue

        # Check if event is today
        if start_dt.date() != today:
            if is_all_day and end_val:
                end_dt, _ = _parse_ical_dt_with_tz(end_val, end_key, cal_tz)
                if end_dt and start_dt.date() <= today < end_dt.date():
                    pass  # multi-day all-day event spanning today
                else:
                    continue
            else:
                continue

        end_dt, _ = _parse_ical_dt_with_tz(end_val, end_key, cal_tz)

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

    # Auto-delete follow-ups completed more than 5 days ago
    five_days_ago = today - timedelta(days=5)
    expired_followups = Note.query.filter(
        Note.author_id == current_user.id,
        Note.follow_up_completed == True,
        Note.follow_up_completed_date != None,
        Note.follow_up_completed_date <= five_days_ago
    ).all()
    for note in expired_followups:
        note.follow_up_needed = False
        note.follow_up_completed = False
        note.follow_up_completed_date = None
    if expired_followups:
        db.session.commit()

    # Follow-ups due (exclude completed ones)
    follow_ups = Note.query.filter(
        Note.author_id == current_user.id,
        Note.follow_up_needed == True,
        Note.follow_up_date <= today + timedelta(days=7),
        db.or_(Note.follow_up_completed == False, Note.follow_up_completed.is_(None))
    ).order_by(Note.follow_up_date).limit(10).all()

    # Archived (completed) follow-ups still within 5-day window
    archived_follow_ups = Note.query.filter(
        Note.author_id == current_user.id,
        Note.follow_up_needed == True,
        Note.follow_up_completed == True,
        Note.follow_up_completed_date != None,
        Note.follow_up_completed_date > five_days_ago
    ).order_by(Note.follow_up_completed_date.desc()).all()

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
        archived_follow_ups=archived_follow_ups,
        total_minutes=total_minutes,
        direct_minutes=direct_minutes,
        indirect_minutes=indirect_minutes,
        mgmt_minutes=mgmt_minutes,
        non_minutes=non_minutes,
        week_activities=week_activities,
    )


@dashboard_bp.route('/follow-up/<int:note_id>/toggle-complete', methods=['POST'])
@login_required
def toggle_follow_up_complete(note_id):
    """Toggle a follow-up note between completed and pending."""
    note = Note.query.get_or_404(note_id)
    if note.author_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    note.follow_up_completed = not note.follow_up_completed
    note.follow_up_completed_date = date.today() if note.follow_up_completed else None
    db.session.commit()
    return jsonify({'completed': note.follow_up_completed})


@dashboard_bp.route('/event/<int:event_id>/toggle-complete', methods=['POST'])
@login_required
def toggle_event_complete(event_id):
    """Toggle an internal calendar event between scheduled and completed."""
    event = CalendarEvent.query.get_or_404(event_id)
    if event.owner_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    event.status = 'scheduled' if event.status == 'completed' else 'completed'
    db.session.commit()
    return jsonify({'status': event.status})
