"""Google Calendar API wrapper — list, create, update, delete events + free/busy."""
from datetime import datetime, timedelta, timezone
from app.utils.google_client import get_credentials


def _service(user):
    """Build a Google Calendar API service for the given user."""
    from googleapiclient.discovery import build
    creds = get_credentials(user)
    if not creds:
        return None
    return build('calendar', 'v3', credentials=creds, cache_discovery=False)


def list_events(user, time_min=None, time_max=None, max_results=250):
    """Fetch events from the user's primary Google Calendar.

    Returns a list of FullCalendar-compatible event dicts.
    """
    svc = _service(user)
    if not svc:
        return []

    if not time_min:
        time_min = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    if not time_max:
        time_max = (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()

    try:
        result = svc.events().list(
            calendarId='primary',
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime',
        ).execute()
    except Exception:
        return []

    events = []
    for item in result.get('items', []):
        start = item.get('start', {})
        end = item.get('end', {})

        is_all_day = 'date' in start
        start_val = start.get('date') or start.get('dateTime', '')
        end_val = end.get('date') or end.get('dateTime', '')

        events.append({
            'id': 'gcal_' + item['id'],
            'title': item.get('summary', '(No title)'),
            'start': start_val,
            'end': end_val,
            'allDay': is_all_day,
            'color': '#DB4437',
            'editable': False,
            'extendedProps': {
                'description': item.get('description', ''),
                'location': item.get('location', ''),
                'event_type': 'google_calendar',
                'source': 'google',
                'google_event_id': item['id'],
                'hangout_link': item.get('hangoutLink', ''),
                'html_link': item.get('htmlLink', ''),
                'attendees': [
                    {'email': a.get('email', ''), 'name': a.get('displayName', ''),
                     'status': a.get('responseStatus', '')}
                    for a in item.get('attendees', [])
                ],
            },
        })

    return events


def create_event(user, summary, start_dt, end_dt, description='',
                 location='', attendees=None, send_updates='all',
                 all_day=False, timezone_str='America/Los_Angeles'):
    """Create an event on the user's primary Google Calendar.

    Args:
        attendees: list of email strings to invite
        send_updates: 'all' sends invite emails, 'none' doesn't

    Returns the created Google Calendar event dict, or None on failure.
    """
    svc = _service(user)
    if not svc:
        return None

    if all_day:
        body = {
            'summary': summary,
            'description': description,
            'location': location,
            'start': {'date': start_dt.strftime('%Y-%m-%d')},
            'end': {'date': end_dt.strftime('%Y-%m-%d')},
        }
    else:
        body = {
            'summary': summary,
            'description': description,
            'location': location,
            'start': {
                'dateTime': start_dt.isoformat(),
                'timeZone': timezone_str,
            },
            'end': {
                'dateTime': end_dt.isoformat(),
                'timeZone': timezone_str,
            },
        }

    if attendees:
        body['attendees'] = [{'email': e} for e in attendees]
        body['guestsCanModify'] = False

    try:
        event = svc.events().insert(
            calendarId='primary',
            body=body,
            sendUpdates=send_updates,
        ).execute()
        return event
    except Exception:
        return None


def update_event(user, google_event_id, updates):
    """Patch an existing Google Calendar event.

    Args:
        updates: dict of fields to update (summary, start, end, description, etc.)

    Returns updated event dict or None.
    """
    svc = _service(user)
    if not svc:
        return None

    try:
        event = svc.events().patch(
            calendarId='primary',
            eventId=google_event_id,
            body=updates,
        ).execute()
        return event
    except Exception:
        return None


def delete_event(user, google_event_id):
    """Delete an event from the user's Google Calendar."""
    svc = _service(user)
    if not svc:
        return False

    try:
        svc.events().delete(
            calendarId='primary',
            eventId=google_event_id,
        ).execute()
        return True
    except Exception:
        return False


def get_freebusy(user, time_min, time_max, timezone_str='America/Los_Angeles'):
    """Query free/busy information for the user's primary calendar.

    Returns a list of busy time ranges: [{'start': iso, 'end': iso}, ...]
    """
    svc = _service(user)
    if not svc:
        return []

    body = {
        'timeMin': time_min if isinstance(time_min, str) else time_min.isoformat(),
        'timeMax': time_max if isinstance(time_max, str) else time_max.isoformat(),
        'timeZone': timezone_str,
        'items': [{'id': 'primary'}],
    }

    try:
        result = svc.freebusy().query(body=body).execute()
        busy = result.get('calendars', {}).get('primary', {}).get('busy', [])
        return busy
    except Exception:
        return []


def list_calendars(user):
    """List all calendars the user has access to."""
    svc = _service(user)
    if not svc:
        return []

    try:
        result = svc.calendarList().list().execute()
        return [
            {'id': c['id'], 'summary': c.get('summary', ''),
             'primary': c.get('primary', False)}
            for c in result.get('items', [])
        ]
    except Exception:
        return []
