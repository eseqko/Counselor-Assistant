"""Slot-finding helpers shared between the public booking page and the
cohort auto-scheduler. Walks AvailabilitySlot definitions, subtracts existing
Bookings and (optionally) Google freebusy, and yields concrete open windows.
"""
from datetime import datetime, date, timedelta, timezone

from app.models.availability import AvailabilitySlot, Booking
from app.utils import google_client, google_calendar


def find_available_slots(user, days_ahead=14, exclude=None,
                         min_duration=None, buffer_min=0,
                         daily_cap=None, duration_override=None):
    """Return concrete open slots for `user` in the next `days_ahead` days.

    Each item: {date, day_name, start_time, end_time, display, duration}.

    Args:
        user: User whose AvailabilitySlots and Bookings we walk.
        days_ahead: how many days forward to search (capped at 30).
        exclude: extra (date_iso, start_time) tuples to treat as taken — used by
            the auto-scheduler to avoid reusing a slot already assigned earlier
            in the same preview run.
        min_duration: if set, only emit slots whose duration is >= this many
            minutes. Used by the group-meeting path to find one window large
            enough for the whole group.
        buffer_min, daily_cap, duration_override: reserved for future
            restriction bundles ("buffer between appointments", "no more than N
            per day"). Accepted today but not enforced.
    """
    days_ahead = min(int(days_ahead), 30)
    today = date.today()
    excluded_set = set(exclude or [])

    slots = (AvailabilitySlot.query
             .filter_by(counselor_id=user.id, is_active=True)
             .order_by(AvailabilitySlot.day_of_week, AvailabilitySlot.start_time)
             .all())

    if not slots:
        return []

    existing_bookings = (Booking.query
                         .filter_by(counselor_id=user.id)
                         .filter(Booking.appointment_date >= today)
                         .filter(Booking.appointment_date <= today + timedelta(days=days_ahead))
                         .filter(Booking.status != 'cancelled')
                         .all())
    booked_set = {(b.appointment_date.isoformat(), b.start_time) for b in existing_bookings}
    booked_set |= excluded_set

    busy_ranges = []
    if google_client.is_connected(user):
        time_min = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
        time_max = datetime.combine(today + timedelta(days=days_ahead),
                                    datetime.max.time()).replace(tzinfo=timezone.utc)
        busy_ranges = google_calendar.get_freebusy(user, time_min, time_max)

    available = []
    for day_offset in range(days_ahead):
        check_date = today + timedelta(days=day_offset)
        dow = check_date.weekday()
        day_slots = [s for s in slots if s.day_of_week == dow]
        if not day_slots:
            continue

        for slot in day_slots:
            start_h, start_m = map(int, slot.start_time.split(':'))
            end_h, end_m = map(int, slot.end_time.split(':'))
            slot_start = start_h * 60 + start_m
            slot_end = end_h * 60 + end_m
            duration = slot.slot_duration

            if min_duration is not None and duration < min_duration:
                continue

            t = slot_start
            while t + duration <= slot_end:
                h, m = divmod(t, 60)
                eh, em = divmod(t + duration, 60)
                time_str = f'{h:02d}:{m:02d}'
                end_str = f'{eh:02d}:{em:02d}'

                if (check_date.isoformat(), time_str) in booked_set:
                    t += duration
                    continue

                if busy_ranges and _is_busy(check_date, time_str, end_str, busy_ranges):
                    t += duration
                    continue

                if check_date == today:
                    now = datetime.now()
                    if h < now.hour or (h == now.hour and m <= now.minute):
                        t += duration
                        continue

                available.append({
                    'date': check_date.isoformat(),
                    'day_name': AvailabilitySlot.DAY_NAMES[dow],
                    'start_time': time_str,
                    'end_time': end_str,
                    'display': f'{_fmt_time(time_str)} - {_fmt_time(end_str)}',
                    'duration': duration,
                })
                t += duration

    return available


def has_upcoming_booking(student, user):
    """True if `student` already has an upcoming, non-cancelled Booking with `user`."""
    return Booking.query.filter_by(
        counselor_id=user.id, student_id=student.id
    ).filter(
        Booking.appointment_date >= date.today(),
        Booking.status != 'cancelled',
    ).first() is not None


def _is_busy(check_date, start_str, end_str, busy_ranges):
    """Check if a time slot overlaps with any busy ranges from Google Calendar."""
    # Availability times are LOCAL wall-clock (e.g. 09:00 Pacific). Google
    # free/busy ranges come back as true UTC. Tagging the wall-clock as UTC
    # (the old behavior) skewed every slot by 7-8h, so a 9am Pacific meeting
    # didn't overlap the 9am slot and busy times were missed -> double-booking.
    # Localize to the same tz get_freebusy() uses (America/Los_Angeles), with
    # DST handled by pytz.localize().
    import pytz
    local_tz = pytz.timezone('America/Los_Angeles')
    slot_start = local_tz.localize(
        datetime.combine(check_date, datetime.strptime(start_str, '%H:%M').time()))
    slot_end = local_tz.localize(
        datetime.combine(check_date, datetime.strptime(end_str, '%H:%M').time()))
    for busy in busy_ranges:
        try:
            b_start = datetime.fromisoformat(busy['start'].replace('Z', '+00:00'))
            b_end = datetime.fromisoformat(busy['end'].replace('Z', '+00:00'))
            if slot_start < b_end and slot_end > b_start:
                return True
        except (ValueError, KeyError):
            continue
    return False


def _fmt_time(time_str):
    """Convert HH:MM to 12-hour format."""
    h, m = map(int, time_str.split(':'))
    period = 'AM' if h < 12 else 'PM'
    display_h = h % 12 or 12
    return f'{display_h}:{m:02d} {period}'
