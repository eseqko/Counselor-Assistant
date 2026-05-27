from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, Response, abort
from flask_login import login_required, current_user
from app import db, csrf
from app.models.availability import Booking
from app.models.calendar_event import CalendarEvent
from app.models.student import Student
from app.models.user import User
from app.utils.audit import log_action
from app.utils import google_client, google_calendar
from app.utils.ics import build_ical_feed
from datetime import datetime, date, timedelta, timezone
from dateutil.rrule import rrulestr
import pytz
import re
import requests as http_requests

calendar_bp = Blueprint('calendar', __name__)


@calendar_bp.route('/')
@login_required
def index():
    view = request.args.get('view', 'month')
    date_str = request.args.get('date', '')

    if date_str:
        try:
            current_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            current_date = date.today()
    else:
        current_date = date.today()

    google_connected = google_client.is_connected(current_user)
    return render_template('calendar/index.html',
        current_date=current_date, view=view,
        event_types=CalendarEvent.EVENT_TYPES,
        event_colors=CalendarEvent.EVENT_COLORS,
        google_connected=google_connected)


@calendar_bp.route('/events')
@login_required
def get_events():
    start = request.args.get('start', '')
    end = request.args.get('end', '')

    query = CalendarEvent.query.filter_by(owner_id=current_user.id)

    if start:
        query = query.filter(CalendarEvent.start_datetime >= start)
    if end:
        query = query.filter(CalendarEvent.end_datetime <= end)

    events = query.all()
    event_list = []
    for e in events:
        event_list.append({
            'id': e.id,
            'title': e.title,
            'start': e.start_datetime.isoformat(),
            'end': e.end_datetime.isoformat(),
            'color': e.color or CalendarEvent.EVENT_COLORS.get(e.event_type, '#4A90D9'),
            'allDay': e.all_day,
            'extendedProps': {
                'description': e.description or '',
                'location': e.location or '',
                'event_type': e.event_type,
                'status': e.status,
                'student_id': e.student_id,
            }
        })

    return jsonify(event_list)


@calendar_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_event():
    if request.method == 'POST':
        start_str = request.form.get('start_datetime', '')
        end_str = request.form.get('end_datetime', '')
        all_day = 'all_day' in request.form

        try:
            start_dt = datetime.strptime(start_str, '%Y-%m-%dT%H:%M')
            end_dt = datetime.strptime(end_str, '%Y-%m-%dT%H:%M') if end_str else start_dt + timedelta(hours=1)
        except ValueError:
            flash('Invalid date/time format.', 'danger')
            return redirect(url_for('calendar.index'))

        event_type = request.form.get('event_type', 'appointment')
        event = CalendarEvent(
            owner_id=current_user.id,
            title=request.form['title'],
            description=request.form.get('description', ''),
            location=request.form.get('location', ''),
            start_datetime=start_dt,
            end_datetime=end_dt,
            all_day=all_day,
            event_type=event_type,
            color=CalendarEvent.EVENT_COLORS.get(event_type, '#4A90D9'),
            student_id=int(request.form['student_id']) if request.form.get('student_id') else None,
            reminder_minutes=int(request.form.get('reminder_minutes', 15)),
        )
        db.session.add(event)
        db.session.commit()
        log_action('create', 'calendar_event', event.id)
        flash('Event added.', 'success')
        return redirect(url_for('calendar.index'))

    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active'
    ).order_by(Student.last_name).all()
    return render_template('calendar/add.html',
        students=students,
        event_types=CalendarEvent.EVENT_TYPES,
        event_colors=CalendarEvent.EVENT_COLORS)


@calendar_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_event(id):
    event = CalendarEvent.query.get_or_404(id)

    if request.method == 'POST':
        event.title = request.form['title']
        event.description = request.form.get('description', '')
        event.location = request.form.get('location', '')
        event.event_type = request.form.get('event_type', 'appointment')
        event.color = CalendarEvent.EVENT_COLORS.get(event.event_type, '#4A90D9')
        event.all_day = 'all_day' in request.form
        event.student_id = int(request.form['student_id']) if request.form.get('student_id') else None
        event.status = request.form.get('status', 'scheduled')

        try:
            event.start_datetime = datetime.strptime(request.form['start_datetime'], '%Y-%m-%dT%H:%M')
            end_str = request.form.get('end_datetime', '')
            event.end_datetime = datetime.strptime(end_str, '%Y-%m-%dT%H:%M') if end_str else event.start_datetime + timedelta(hours=1)
        except ValueError:
            flash('Invalid date/time.', 'danger')

        db.session.commit()
        log_action('update', 'calendar_event', event.id)
        flash('Event updated.', 'success')
        return redirect(url_for('calendar.index'))

    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active'
    ).order_by(Student.last_name).all()
    return render_template('calendar/edit.html', event=event, students=students,
        event_types=CalendarEvent.EVENT_TYPES, event_colors=CalendarEvent.EVENT_COLORS)


@calendar_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete_event(id):
    event = CalendarEvent.query.get_or_404(id)
    log_action('delete', 'calendar_event', event.id)
    db.session.delete(event)
    db.session.commit()
    flash('Event deleted.', 'warning')
    return redirect(url_for('calendar.index'))


@calendar_bp.route('/feed-url')
@login_required
def feed_url():
    """Generate and return the user's personal iCal feed URL."""
    token = current_user.get_or_create_feed_token()
    feed_link = url_for('calendar.ical_feed', token=token, _external=True)
    return jsonify({'feed_url': feed_link})


@calendar_bp.route('/feed/<token>.ics')
def ical_feed(token):
    """Public iCal feed endpoint — authenticated by unique token, no login required.

    Emits both CalendarEvents (counselor's own events) and confirmed Bookings
    (parent/cohort-booked appointments) so subscribed Google Calendars see
    everything the app considers scheduled.
    """
    user = User.query.filter_by(calendar_feed_token=token).first()
    if not user:
        abort(404)

    events = CalendarEvent.query.filter_by(owner_id=user.id).filter(
        CalendarEvent.status != 'cancelled'
    ).all()
    bookings = Booking.query.filter_by(counselor_id=user.id).filter(
        Booking.status != 'cancelled'
    ).all()

    ics_content = build_ical_feed(user, calendar_events=events, bookings=bookings)
    return Response(ics_content, mimetype='text/calendar',
                    headers={'Content-Disposition': 'inline; filename="calendar.ics"'})


@calendar_bp.route('/google-events')
@login_required
def get_google_events():
    """Fetch events via Google Calendar API (OAuth) — preferred over iCal."""
    if not google_client.is_connected(current_user):
        return jsonify([])

    start = request.args.get('start', '')
    end = request.args.get('end', '')
    events = google_calendar.list_events(current_user, time_min=start or None,
                                         time_max=end or None)
    return jsonify(events)


@calendar_bp.route('/api/create-google-event', methods=['POST'])
@csrf.exempt
@login_required
def create_google_event():
    """Create an event on Google Calendar from the app."""
    if not google_client.is_connected(current_user):
        return jsonify({'error': 'Google Calendar not connected.'}), 400

    data = request.get_json(silent=True) or {}
    summary = data.get('title', '').strip()
    if not summary:
        return jsonify({'error': 'Title is required.'}), 400

    try:
        start_dt = datetime.fromisoformat(data['start'])
        end_str = data.get('end', '')
        end_dt = datetime.fromisoformat(end_str) if end_str else start_dt + timedelta(hours=1)
    except (ValueError, KeyError):
        return jsonify({'error': 'Invalid date/time.'}), 400

    attendees = data.get('attendees', [])
    if isinstance(attendees, str):
        attendees = [e.strip() for e in attendees.split(',') if e.strip()]

    gcal_event = google_calendar.create_event(
        current_user, summary, start_dt, end_dt,
        description=data.get('description', ''),
        location=data.get('location', ''),
        attendees=attendees or None,
        all_day=data.get('all_day', False),
    )

    if not gcal_event:
        return jsonify({'error': 'Failed to create Google Calendar event.'}), 500

    return jsonify({
        'ok': True,
        'google_event_id': gcal_event.get('id'),
        'html_link': gcal_event.get('htmlLink', ''),
    }), 201


@calendar_bp.route('/external-ical', methods=['GET', 'POST'])
@login_required
def external_ical():
    """Save or remove the user's external Google Calendar iCal URL."""
    if request.method == 'POST':
        ical_url = request.form.get('external_ical_url', '').strip()
        if ical_url and not ical_url.startswith(('http://', 'https://')):
            flash('Please enter a valid URL starting with https://', 'danger')
            return redirect(url_for('calendar.index'))
        current_user.external_ical_url = ical_url or None
        db.session.commit()
        if ical_url:
            flash('Google Calendar connected successfully.', 'success')
        else:
            flash('Google Calendar disconnected.', 'info')
        return redirect(url_for('calendar.index'))
    return jsonify({'external_ical_url': current_user.external_ical_url or ''})


@calendar_bp.route('/external-events')
@login_required
def get_external_events():
    """Fetch and return events from the user's external iCal feed."""
    if not current_user.external_ical_url:
        return jsonify([])

    try:
        resp = http_requests.get(current_user.external_ical_url, timeout=3)
        resp.raise_for_status()
        events = _parse_ical_feed(resp.text)
        return jsonify(events)
    except Exception:
        return jsonify([])


def _parse_ical_feed(ics_text):
    """Parse an iCal feed and return a list of FullCalendar-compatible event dicts."""
    events = []
    # Unfold lines (iCal continuation lines start with space or tab)
    ics_text = re.sub(r'\r?\n[ \t]', '', ics_text)

    # Build a lookup of VTIMEZONE definitions for TZID resolution
    tz_map = {}
    for tz_block in re.findall(r'BEGIN:VTIMEZONE(.*?)END:VTIMEZONE', ics_text, re.DOTALL):
        m = re.search(r'TZID:(.*)', tz_block)
        if m:
            tz_map[m.group(1).strip()] = True

    # Window for recurring event expansion: 90 days before/after today
    window_start = datetime.now(timezone.utc) - timedelta(days=90)
    window_end = datetime.now(timezone.utc) + timedelta(days=90)

    blocks = re.split(r'BEGIN:VEVENT', ics_text)

    for block in blocks[1:]:  # skip preamble before first VEVENT
        block = block.split('END:VEVENT')[0]

        # Parse properties, preserving full key (with params) and base key
        props = {}       # base_key -> value
        full_keys = {}   # base_key -> full key with params
        for line in block.strip().splitlines():
            if ':' in line:
                key, _, value = line.partition(':')
                base_key = key.split(';')[0].strip()
                props[base_key] = value.strip()
                full_keys[base_key] = key.strip()

        title = _ical_unescape(props.get('SUMMARY', 'Google Calendar Event'))
        description = _ical_unescape(props.get('DESCRIPTION', ''))
        location = _ical_unescape(props.get('LOCATION', ''))

        # Extract TZID from DTSTART parameters if present
        dtstart_key = full_keys.get('DTSTART', '')
        tzid = None
        tzid_match = re.search(r'TZID=([^;:]+)', dtstart_key)
        if tzid_match:
            tzid = tzid_match.group(1)

        start_val = props.get('DTSTART', '')
        end_val = props.get('DTEND', '')

        start_dt = _parse_ical_datetime_tz(start_val, tzid)
        end_dt = _parse_ical_datetime_tz(end_val, tzid)
        if not start_dt:
            continue

        # Detect all-day events
        is_all_day = False
        for line in block.strip().splitlines():
            if line.startswith('DTSTART') and 'VALUE=DATE' in line:
                is_all_day = True
                break

        # Calculate event duration for recurring instances
        duration = None
        if start_dt and end_dt and not is_all_day:
            duration = end_dt - start_dt

        # Handle recurring events with RRULE
        rrule_str = props.get('RRULE', '')
        exdate_strs = [line.partition(':')[2].strip()
                       for line in block.strip().splitlines()
                       if line.startswith('EXDATE')]

        if rrule_str and not is_all_day:
            try:
                # Build full RRULE string for dateutil
                rule = rrulestr(
                    f"DTSTART:{start_val}\nRRULE:{rrule_str}",
                    ignoretz=True
                )
                # Parse excluded dates
                excluded = set()
                for exd in exdate_strs:
                    for part in exd.split(','):
                        part = part.strip().replace('Z', '')
                        try:
                            excluded.add(datetime.strptime(part[:15], '%Y%m%dT%H%M%S'))
                        except ValueError:
                            pass

                for occ_start in rule.between(window_start, window_end, inc=True):
                    if occ_start in excluded:
                        continue
                    occ_end = occ_start + duration if duration else None
                    # Apply same timezone conversion as the original event
                    occ_start_utc = _apply_tz(occ_start, start_val, tzid)
                    occ_end_utc = _apply_tz(occ_end, end_val, tzid) if occ_end else None

                    evt = _build_event(title, occ_start_utc, occ_end_utc,
                                       is_all_day, description, location)
                    events.append(evt)
            except Exception:
                # Fall back to single instance if RRULE parsing fails
                start_iso = _format_dt_iso(start_dt, start_val, tzid, is_all_day)
                end_iso = _format_dt_iso(end_dt, end_val, tzid, is_all_day) if end_dt else None
                events.append(_build_event(title, start_iso, end_iso,
                                           is_all_day, description, location))
        else:
            start_iso = _format_dt_iso(start_dt, start_val, tzid, is_all_day)
            end_iso = _format_dt_iso(end_dt, end_val, tzid, is_all_day) if end_dt else None
            events.append(_build_event(title, start_iso, end_iso,
                                       is_all_day, description, location))

    return events


def _build_event(title, start, end, all_day, description, location):
    """Build a FullCalendar-compatible event dict."""
    event = {
        'title': title,
        'start': start,
        'color': '#DB4437',
        'allDay': all_day,
        'editable': False,
        'extendedProps': {
            'description': description,
            'location': location,
            'event_type': 'google_calendar',
            'source': 'google',
        }
    }
    if end:
        event['end'] = end
    return event


def _parse_ical_datetime_tz(value, tzid=None):
    """Parse an iCal datetime string into a naive datetime object (for calculations)."""
    if not value:
        return None
    clean = value.replace('Z', '')
    try:
        if len(clean) == 8:
            return datetime.strptime(clean, '%Y%m%d')
        elif 'T' in clean:
            return datetime.strptime(clean, '%Y%m%dT%H%M%S')
    except ValueError:
        pass
    return None


def _apply_tz(dt, raw_value, tzid):
    """Convert a naive datetime to a UTC ISO string based on the original timezone info."""
    if dt is None:
        return None
    # If original value was UTC (ends with Z), localize as UTC
    if isinstance(raw_value, str) and raw_value.endswith('Z'):
        return dt.strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
    # If a TZID was specified, convert from that timezone to UTC
    if tzid:
        try:
            tz = pytz.timezone(tzid)
            localized = tz.localize(dt)
            utc_dt = localized.astimezone(pytz.utc)
            return utc_dt.strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
        except (pytz.exceptions.UnknownTimeZoneError, Exception):
            pass
    # Floating time — return as-is (no timezone info, FullCalendar uses browser tz)
    return dt.isoformat()


def _format_dt_iso(dt, raw_value, tzid, is_all_day):
    """Format a parsed datetime as an ISO string for FullCalendar, preserving tz info."""
    if dt is None:
        return None
    if is_all_day:
        return dt.strftime('%Y-%m-%d')
    return _apply_tz(dt, raw_value, tzid)


def _ical_unescape(text):
    """Unescape iCal text fields."""
    return text.replace('\\n', '\n').replace('\\,', ',').replace('\\;', ';').replace('\\\\', '\\')
