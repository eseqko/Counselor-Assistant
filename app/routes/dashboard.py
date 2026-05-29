from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.calendar_event import CalendarEvent
from app.models.note import Note
from app.models.activity import Activity
from app.models.transcript import TranscriptRecord
from app.utils.alert_engine import get_alerts
from app.utils.caseload import caseload_student_ids
from sqlalchemy import func as sa_func
from datetime import datetime, date, timedelta
import json
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
        resp = http_requests.get(user.external_ical_url, timeout=3)
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

    # Stats — single query for student IDs (reused for count + grad risk)
    my_student_ids = caseload_student_ids(current_user, status='active')
    total_students = len(my_student_ids)

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

    # Graduation at-risk summary from transcript records
    grad_risk = {'critical': 0, 'at-risk': 0, 'warning': 0, 'on-track': 0}
    if my_student_ids:
        seen = set()
        transcripts = TranscriptRecord.query.filter(
            TranscriptRecord.student_id.in_(my_student_ids)
        ).order_by(TranscriptRecord.import_date.desc()).all()
        for tr in transcripts:
            if tr.student_id not in seen:
                seen.add(tr.student_id)
                rl = tr.risk_level or 'unknown'
                if rl in grad_risk:
                    grad_risk[rl] += 1
    grad_at_risk_total = grad_risk['critical'] + grad_risk['at-risk']

    # Smart alerts (cached by day — fast after first load)
    alerts = get_alerts(current_user)
    alert_counts = {}
    for a in alerts:
        p = a.get('priority_label', 'low')
        alert_counts[p] = alert_counts.get(p, 0) + 1
    critical_alerts = [a for a in alerts if a.get('priority_label') in ('critical', 'high')]

    # ── Chart data ────────────────────────────────────────────────
    # 1) Note activity trend — notes per week for last 8 weeks (one query, bucket in Python)
    trend_start = today - timedelta(days=today.weekday() + 7 * 7)
    trend_dates = db.session.query(Note.session_date).filter(
        Note.author_id == current_user.id,
        Note.session_date >= trend_start,
        Note.session_date <= today,
    ).all()
    week_counts = {}
    for (sd,) in trend_dates:
        if sd is None:
            continue
        wk_start = sd - timedelta(days=sd.weekday())
        week_counts[wk_start] = week_counts.get(wk_start, 0) + 1
    note_trend = []
    for i in range(7, -1, -1):
        wk_start = today - timedelta(days=today.weekday() + 7 * i)
        note_trend.append({'label': wk_start.strftime('%m/%d'),
                           'count': week_counts.get(wk_start, 0)})

    # 2) Note category breakdown — all-time counts by note_type
    note_type_labels = dict(Note.NOTE_TYPES)
    note_type_rows = db.session.query(
        Note.note_type, sa_func.count(Note.id)
    ).filter_by(author_id=current_user.id).group_by(
        Note.note_type
    ).all()
    svc_breakdown = {note_type_labels.get(k, k): v for k, v in note_type_rows}

    return render_template('dashboard/index.html',
        today=today,
        total_students=total_students,
        todays_events=todays_events,
        external_events=[],
        all_event_count=len(todays_events),
        recent_notes=recent_notes,
        follow_ups=follow_ups,
        archived_follow_ups=archived_follow_ups,
        total_minutes=total_minutes,
        direct_minutes=direct_minutes,
        indirect_minutes=indirect_minutes,
        mgmt_minutes=mgmt_minutes,
        non_minutes=non_minutes,
        week_activities=week_activities,
        grad_risk=grad_risk,
        grad_at_risk_total=grad_at_risk_total,
        alerts=alerts,
        alert_counts=alert_counts,
        critical_alerts=critical_alerts,
        note_trend_json=json.dumps(note_trend),
        svc_breakdown_json=json.dumps(svc_breakdown),
        grad_risk_json=json.dumps(grad_risk),
    )


@dashboard_bp.route('/api/external-events')
@login_required
def external_events_api():
    """Fetch external iCal events asynchronously so they don't block page load."""
    events = _fetch_todays_external_events(current_user)
    result = []
    for e in events:
        result.append({
            'title': e['title'],
            'start': e['start_datetime'].strftime('%I:%M %p') if not e.get('is_all_day') else 'All day',
            'end': e['end_datetime'].strftime('%I:%M %p') if e.get('end_datetime') and not e.get('is_all_day') else '',
            'location': e.get('location', ''),
            'is_all_day': e.get('is_all_day', False),
        })
    return jsonify({'events': result, 'count': len(result)})


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
