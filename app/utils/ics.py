"""Shared iCalendar (.ics) generation.

The counselor's published feed at /calendar/feed/<token>.ics and the
auto-scheduler's batch-download both build VEVENT blocks from the same model
rows — this module is the one place where that VEVENT formatting lives.
"""
from datetime import datetime, timezone

from app.models.availability import Booking
from app.models.calendar_event import CalendarEvent


def build_ical_feed(user, calendar_events=None, bookings=None,
                    calname_suffix='Counselor Calendar'):
    """Build a full iCalendar document from CalendarEvents and Bookings.

    Either iterable may be None or empty. Each item is rendered as one VEVENT.
    """
    calendar_events = calendar_events or []
    bookings = bookings or []

    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//Counselor Assistant//Calendar Feed//EN',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        f'X-WR-CALNAME:{user.display_name} - {calname_suffix}',
    ]

    for e in calendar_events:
        lines.extend(_vevent_for_calendar_event(e))

    for b in bookings:
        lines.extend(_vevent_for_booking(b))

    lines.append('END:VCALENDAR')
    return '\r\n'.join(lines) + '\r\n'


def _vevent_for_calendar_event(e):
    """Render a CalendarEvent as a list of iCal VEVENT lines."""
    lines = [
        'BEGIN:VEVENT',
        f'UID:event-{e.id}@counselor-assistant',
        f'DTSTAMP:{_ical_dt(e.created_at or datetime.now(timezone.utc))}',
    ]
    if e.all_day:
        lines.append(f'DTSTART;VALUE=DATE:{e.start_datetime.strftime("%Y%m%d")}')
        lines.append(f'DTEND;VALUE=DATE:{e.end_datetime.strftime("%Y%m%d")}')
    else:
        lines.append(f'DTSTART:{_ical_dt(e.start_datetime)}')
        lines.append(f'DTEND:{_ical_dt(e.end_datetime)}')
    lines.append(f'SUMMARY:{_ical_escape(e.title)}')
    if e.description:
        lines.append(f'DESCRIPTION:{_ical_escape(e.description)}')
    if e.location:
        lines.append(f'LOCATION:{_ical_escape(e.location)}')
    if e.event_type:
        lines.append(f'CATEGORIES:{e.event_type.replace("_", " ").title()}')
    if e.reminder_minutes:
        lines.append('BEGIN:VALARM')
        lines.append('ACTION:DISPLAY')
        lines.append(f'TRIGGER:-PT{e.reminder_minutes}M')
        lines.append(f'DESCRIPTION:Reminder: {_ical_escape(e.title)}')
        lines.append('END:VALARM')
    lines.append('END:VEVENT')
    return lines


def _vevent_for_booking(b):
    """Render a Booking as a list of iCal VEVENT lines."""
    meeting_label = dict(Booking.MEETING_TYPES).get(b.meeting_type, b.meeting_type)
    student_info = f' — {b.student_name}' if b.student_name else ''
    summary = f'{meeting_label}: {b.booker_name}{student_info}'

    description_parts = [f'Booked by: {b.booker_name}']
    if b.booker_relationship:
        description_parts.append(f'Relationship: {b.booker_relationship}')
    if b.student_name:
        description_parts.append(f'Student: {b.student_name}')
    description_parts.append(f'Type: {meeting_label}')
    if b.notes:
        description_parts.append(f'Notes: {b.notes}')
    description = '\n'.join(description_parts)

    start_dt = datetime.combine(b.appointment_date,
                                datetime.strptime(b.start_time, '%H:%M').time())
    end_dt = datetime.combine(b.appointment_date,
                              datetime.strptime(b.end_time, '%H:%M').time())

    lines = [
        'BEGIN:VEVENT',
        f'UID:booking-{b.id}@counselor-assistant',
        f'DTSTAMP:{_ical_dt(b.created_at or datetime.now(timezone.utc))}',
        f'DTSTART:{_ical_dt(start_dt)}',
        f'DTEND:{_ical_dt(end_dt)}',
        f'SUMMARY:{_ical_escape(summary)}',
        f'DESCRIPTION:{_ical_escape(description)}',
        'CATEGORIES:Booking',
        'END:VEVENT',
    ]
    return lines


def _ical_dt(dt):
    """Format a datetime as an iCal UTC timestamp."""
    return dt.strftime('%Y%m%dT%H%M%SZ')


def _ical_escape(text):
    """Escape special characters for iCal text fields."""
    if text is None:
        return ''
    return (text.replace('\\', '\\\\')
                .replace(';', '\\;')
                .replace(',', '\\,')
                .replace('\n', '\\n'))
