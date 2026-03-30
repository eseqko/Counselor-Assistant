"""Availability management and public booking page."""
from datetime import datetime, date, timedelta, timezone
from flask import Blueprint, render_template, request, jsonify, abort
from flask_login import login_required, current_user
from app import db, csrf
from app.models.availability import AvailabilitySlot, Booking
from app.models.user import User
from app.utils import google_client, google_calendar

availability_bp = Blueprint('availability', __name__)


# ── Counselor: manage availability ────────────────────────────────

@availability_bp.route('/')
@login_required
def index():
    slots = (AvailabilitySlot.query
             .filter_by(counselor_id=current_user.id)
             .order_by(AvailabilitySlot.day_of_week, AvailabilitySlot.start_time)
             .all())
    bookings = (Booking.query
                .filter_by(counselor_id=current_user.id)
                .filter(Booking.appointment_date >= date.today())
                .filter(Booking.status != 'cancelled')
                .order_by(Booking.appointment_date, Booking.start_time)
                .all())
    google_connected = google_client.is_connected(current_user)
    booking_token = current_user.get_or_create_feed_token()
    return render_template('availability/index.html',
                           slots=slots, bookings=bookings,
                           google_connected=google_connected,
                           booking_token=booking_token,
                           day_names=AvailabilitySlot.DAY_NAMES,
                           meeting_types=Booking.MEETING_TYPES)


@availability_bp.route('/api/slots', methods=['GET', 'POST'])
@csrf.exempt
@login_required
def api_slots():
    if request.method == 'GET':
        slots = (AvailabilitySlot.query
                 .filter_by(counselor_id=current_user.id)
                 .order_by(AvailabilitySlot.day_of_week, AvailabilitySlot.start_time)
                 .all())
        return jsonify([s.to_dict() for s in slots])

    data = request.get_json(silent=True) or {}
    day = data.get('day_of_week')
    start = data.get('start_time', '').strip()
    end = data.get('end_time', '').strip()
    duration = data.get('slot_duration', 30)

    if day is None or not start or not end:
        return jsonify({'error': 'Day, start time, and end time are required.'}), 400
    if int(day) < 0 or int(day) > 6:
        return jsonify({'error': 'Invalid day of week.'}), 400

    slot = AvailabilitySlot(
        counselor_id=current_user.id,
        day_of_week=int(day),
        start_time=start,
        end_time=end,
        slot_duration=int(duration),
    )
    db.session.add(slot)
    db.session.commit()
    return jsonify(slot.to_dict()), 201


@availability_bp.route('/api/slots/<int:slot_id>', methods=['DELETE'])
@csrf.exempt
@login_required
def api_delete_slot(slot_id):
    slot = AvailabilitySlot.query.get_or_404(slot_id)
    if slot.counselor_id != current_user.id:
        abort(403)
    db.session.delete(slot)
    db.session.commit()
    return jsonify({'ok': True})


@availability_bp.route('/api/bookings')
@csrf.exempt
@login_required
def api_bookings():
    bookings = (Booking.query
                .filter_by(counselor_id=current_user.id)
                .filter(Booking.appointment_date >= date.today())
                .filter(Booking.status != 'cancelled')
                .order_by(Booking.appointment_date, Booking.start_time)
                .all())
    return jsonify([b.to_dict() for b in bookings])


@availability_bp.route('/api/bookings/<int:booking_id>/cancel', methods=['POST'])
@csrf.exempt
@login_required
def api_cancel_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.counselor_id != current_user.id:
        abort(403)
    booking.status = 'cancelled'

    # Cancel on Google Calendar too
    if booking.google_event_id and google_client.is_connected(current_user):
        google_calendar.delete_event(current_user, booking.google_event_id)

    db.session.commit()
    return jsonify({'ok': True})


# ── Public booking page (no login required) ───────────────────────

@availability_bp.route('/book/<token>')
def public_booking_page(token):
    """Public-facing page where parents/students can book an appointment."""
    user = User.query.filter_by(calendar_feed_token=token).first()
    if not user:
        abort(404)
    return render_template('availability/book.html',
                           counselor=user, token=token,
                           meeting_types=Booking.MEETING_TYPES)


@availability_bp.route('/book/<token>/slots')
def public_available_slots(token):
    """Return available time slots for the next N days."""
    user = User.query.filter_by(calendar_feed_token=token).first()
    if not user:
        abort(404)

    days_ahead = min(int(request.args.get('days', 14)), 30)
    today = date.today()
    slots = (AvailabilitySlot.query
             .filter_by(counselor_id=user.id, is_active=True)
             .order_by(AvailabilitySlot.day_of_week, AvailabilitySlot.start_time)
             .all())

    if not slots:
        return jsonify([])

    # Get existing bookings to exclude
    existing_bookings = (Booking.query
                         .filter_by(counselor_id=user.id)
                         .filter(Booking.appointment_date >= today)
                         .filter(Booking.appointment_date <= today + timedelta(days=days_ahead))
                         .filter(Booking.status != 'cancelled')
                         .all())
    booked_set = set()
    for b in existing_bookings:
        booked_set.add((b.appointment_date.isoformat(), b.start_time))

    # Get Google Calendar busy times if connected
    busy_ranges = []
    if google_client.is_connected(user):
        time_min = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
        time_max = datetime.combine(today + timedelta(days=days_ahead),
                                    datetime.max.time()).replace(tzinfo=timezone.utc)
        busy_ranges = google_calendar.get_freebusy(user, time_min, time_max)

    # Generate available slots for each day
    available = []
    for day_offset in range(days_ahead):
        check_date = today + timedelta(days=day_offset)
        dow = check_date.weekday()  # 0=Mon

        day_slots = [s for s in slots if s.day_of_week == dow]
        if not day_slots:
            continue

        for slot in day_slots:
            # Generate individual bookable time blocks
            start_h, start_m = map(int, slot.start_time.split(':'))
            end_h, end_m = map(int, slot.end_time.split(':'))
            slot_start = start_h * 60 + start_m
            slot_end = end_h * 60 + end_m
            duration = slot.slot_duration

            t = slot_start
            while t + duration <= slot_end:
                h, m = divmod(t, 60)
                eh, em = divmod(t + duration, 60)
                time_str = f'{h:02d}:{m:02d}'
                end_str = f'{eh:02d}:{em:02d}'

                # Skip if already booked
                if (check_date.isoformat(), time_str) in booked_set:
                    t += duration
                    continue

                # Skip if conflicts with Google Calendar busy time
                if busy_ranges and _is_busy(check_date, time_str, end_str, busy_ranges):
                    t += duration
                    continue

                # Skip past times today
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
                })
                t += duration

    return jsonify(available)


@availability_bp.route('/book/<token>/confirm', methods=['POST'])
@csrf.exempt
def public_confirm_booking(token):
    """Confirm a booking from the public page."""
    user = User.query.filter_by(calendar_feed_token=token).first()
    if not user:
        abort(404)

    data = request.get_json(silent=True) or {}
    booker_name = data.get('name', '').strip()
    appointment_date = data.get('date', '').strip()
    start_time = data.get('start_time', '').strip()
    end_time = data.get('end_time', '').strip()

    if not booker_name or not appointment_date or not start_time:
        return jsonify({'error': 'Name, date, and time are required.'}), 400

    # Verify slot is still available
    try:
        appt_date = datetime.strptime(appointment_date, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format.'}), 400

    existing = Booking.query.filter_by(
        counselor_id=user.id,
        appointment_date=appt_date,
        start_time=start_time,
    ).filter(Booking.status != 'cancelled').first()

    if existing:
        return jsonify({'error': 'This time slot is no longer available.'}), 409

    booking = Booking(
        counselor_id=user.id,
        booker_name=booker_name,
        booker_email=data.get('email', '').strip() or None,
        booker_phone=data.get('phone', '').strip() or None,
        booker_relationship=data.get('relationship', 'parent'),
        student_name=data.get('student_name', '').strip() or None,
        meeting_type=data.get('meeting_type', 'general'),
        notes=data.get('notes', '').strip() or None,
        appointment_date=appt_date,
        start_time=start_time,
        end_time=end_time,
    )
    db.session.add(booking)

    # Create Google Calendar event if connected
    if google_client.is_connected(user):
        student_info = f" — {booking.student_name}" if booking.student_name else ''
        meeting_label = dict(Booking.MEETING_TYPES).get(booking.meeting_type, booking.meeting_type)
        summary = f'{meeting_label}: {booker_name}{student_info}'
        description = (
            f'Booked by: {booker_name}\n'
            f'Relationship: {booking.booker_relationship or "N/A"}\n'
            f'Student: {booking.student_name or "N/A"}\n'
            f'Type: {meeting_label}\n'
        )
        if booking.notes:
            description += f'Notes: {booking.notes}\n'

        start_dt = datetime.combine(appt_date, datetime.strptime(start_time, '%H:%M').time())
        end_dt = datetime.combine(appt_date, datetime.strptime(end_time, '%H:%M').time())

        attendees = [booking.booker_email] if booking.booker_email else None
        gcal_event = google_calendar.create_event(
            user, summary, start_dt, end_dt,
            description=description,
            attendees=attendees,
            send_updates='all' if attendees else 'none',
        )
        if gcal_event:
            booking.google_event_id = gcal_event.get('id')

    db.session.commit()

    return jsonify({
        'ok': True,
        'booking': booking.to_dict(),
        'message': f'Appointment confirmed for {appt_date.strftime("%B %d, %Y")} '
                   f'at {_fmt_time(start_time)}.',
    }), 201


def _is_busy(check_date, start_str, end_str, busy_ranges):
    """Check if a time slot overlaps with any busy ranges from Google Calendar."""
    slot_start = datetime.combine(check_date,
                                  datetime.strptime(start_str, '%H:%M').time(),
                                  tzinfo=timezone.utc)
    slot_end = datetime.combine(check_date,
                                datetime.strptime(end_str, '%H:%M').time(),
                                tzinfo=timezone.utc)

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
