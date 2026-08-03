"""Availability management, public booking page, and cohort auto-scheduling."""
from datetime import datetime, date, timezone
from flask import (Blueprint, render_template, request, jsonify, abort, session,
                   flash, redirect, url_for, Response)
from flask_login import login_required, current_user
from app import db, csrf
from app.models.availability import AvailabilitySlot, Booking
from app.models.calendar_event import CalendarEvent
from app.models.student import Student
from app.models.user import User
from app.utils import google_client, google_calendar
from app.utils.audit import log_action
from app.utils.ratelimit import rate_limit, clamp
from app.utils.ics import build_ical_feed
from app.utils.scheduling import (find_available_slots, has_upcoming_booking,
                                  _fmt_time)

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
    booking_token = current_user.get_or_create_booking_token()
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
    user = User.query.filter_by(booking_token=token).first()
    if not user:
        abort(404)
    return render_template('availability/book.html',
                           counselor=user, token=token,
                           meeting_types=Booking.MEETING_TYPES)


@availability_bp.route('/book/<token>/slots')
def public_available_slots(token):
    """Return available time slots for the next N days."""
    user = User.query.filter_by(booking_token=token).first()
    if not user:
        abort(404)

    days_ahead = min(int(request.args.get('days', 14)), 30)
    return jsonify(find_available_slots(user, days_ahead=days_ahead))


@availability_bp.route('/book/<token>/confirm', methods=['POST'])
@csrf.exempt
# Anonymous + csrf-exempt + persists into the counselor's calendar, so an
# unthrottled endpoint lets one token-holder script hundreds of bookings or
# plant text under a classmate's name.
@rate_limit('public_booking', limit=5, window=300)
def public_confirm_booking(token):
    """Confirm a booking from the public page."""
    user = User.query.filter_by(booking_token=token).first()
    if not user:
        abort(404)

    data = request.get_json(silent=True) or {}
    booker_name = clamp(data.get('name'), 120)
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
        booker_email=clamp(data.get('email'), 200) or None,
        booker_phone=clamp(data.get('phone'), 40) or None,
        booker_relationship=clamp(data.get('relationship'), 40) or 'parent',
        student_name=clamp(data.get('student_name'), 120) or None,
        meeting_type=clamp(data.get('meeting_type'), 40) or 'general',
        notes=clamp(data.get('notes'), 2000) or None,
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


# ── Cohort auto-scheduler ─────────────────────────────────────────

_AB_FIELDS = {
    'is_foster_youth', 'is_homeless', 'is_migrant_newcomer',
    'is_formerly_incarcerated', 'is_military_connected',
}


def _filter_students(user):
    """Apply request.args filters to the caseload and return the matching Students."""
    q = Student.query.filter_by(assigned_counselor_id=user.id, status='active')

    grades = request.args.getlist('grade')
    if grades:
        try:
            q = q.filter(Student.grade_level.in_([int(g) for g in grades if g]))
        except ValueError:
            pass

    el_statuses = request.args.getlist('el_status')
    if el_statuses:
        q = q.filter(Student.el_status.in_(el_statuses))

    el_levels = request.args.getlist('el_level')
    if el_levels:
        q = q.filter(Student.el_level.in_(el_levels))

    if request.args.get('iep_status') == '1':
        q = q.filter(Student.iep_status.is_(True))
    if request.args.get('section_504') == '1':
        q = q.filter(Student.section_504.is_(True))

    for fld in request.args.getlist('ab_population'):
        if fld in _AB_FIELDS:
            q = q.filter(getattr(Student, fld).is_(True))

    search = request.args.get('search', '').strip()
    if search:
        like = f'%{search}%'
        q = q.filter(db.or_(
            Student.first_name.ilike(like),
            Student.last_name.ilike(like),
            Student.student_id_number.ilike(like),
        ))

    return q.order_by(Student.last_name, Student.first_name).all()


@availability_bp.route('/auto')
@login_required
def auto_schedule_picker():
    """Cohort filter + student picker for auto-scheduling."""
    students = _filter_students(current_user)
    slots_exist = AvailabilitySlot.query.filter_by(
        counselor_id=current_user.id, is_active=True
    ).first() is not None

    return render_template('availability/auto_schedule.html',
                           students=students,
                           slots_exist=slots_exist,
                           el_statuses=Student.EL_STATUSES,
                           el_levels=Student.EL_LEVELS,
                           ab_population_fields=Student.AB_POPULATION_FIELDS,
                           meeting_types=Booking.MEETING_TYPES,
                           selected={
                               'grade': request.args.getlist('grade'),
                               'el_status': request.args.getlist('el_status'),
                               'el_level': request.args.getlist('el_level'),
                               'iep_status': request.args.get('iep_status') == '1',
                               'section_504': request.args.get('section_504') == '1',
                               'ab_population': request.args.getlist('ab_population'),
                               'search': request.args.get('search', ''),
                           })


@availability_bp.route('/auto/preview', methods=['POST'])
@login_required
def auto_schedule_preview():
    """Build a proposal: assign each selected student to an open slot."""
    student_ids = [int(sid) for sid in request.form.getlist('student_ids') if sid.isdigit()]
    if not student_ids:
        flash('Select at least one student.', 'warning')
        return redirect(url_for('availability.auto_schedule_picker'))

    mode = request.form.get('mode', 'individual')
    if mode not in ('individual', 'group'):
        mode = 'individual'

    try:
        duration = int(request.form.get('duration', 15))
        days_ahead = int(request.form.get('days_ahead', 14))
    except ValueError:
        flash('Duration and days ahead must be numbers.', 'danger')
        return redirect(url_for('availability.auto_schedule_picker'))
    duration = max(5, min(duration, 240))
    days_ahead = max(1, min(days_ahead, 30))

    title = request.form.get('title', '').strip() or (
        'Cohort check-in' if mode == 'group' else 'Check-in'
    )
    notes = request.form.get('notes', '').strip()
    meeting_type = request.form.get('meeting_type', 'general')

    students = (Student.query
                .filter(Student.id.in_(student_ids),
                        Student.assigned_counselor_id == current_user.id)
                .order_by(Student.last_name, Student.first_name)
                .all())

    proposal = {
        'mode': mode, 'title': title, 'notes': notes,
        'duration': duration, 'days_ahead': days_ahead,
        'meeting_type': meeting_type,
        'items': [], 'unscheduled': [],
        'created_at': datetime.now(timezone.utc).isoformat(),
    }

    if mode == 'individual':
        slots = find_available_slots(current_user, days_ahead=days_ahead)
        for s in students:
            if has_upcoming_booking(s, current_user):
                proposal['unscheduled'].append({
                    'student_id': s.id, 'name': s.display_name,
                    'reason': 'already has an upcoming appointment',
                })
                continue
            if not slots:
                proposal['unscheduled'].append({
                    'student_id': s.id, 'name': s.display_name,
                    'reason': f'no open slot in next {days_ahead} days',
                })
                continue
            slot = slots.pop(0)
            proposal['items'].append({
                'student_id': s.id, 'name': s.display_name,
                'date': slot['date'], 'day_name': slot['day_name'],
                'start_time': slot['start_time'], 'end_time': slot['end_time'],
                'display': slot['display'],
            })
    else:  # group
        slots = find_available_slots(current_user, days_ahead=days_ahead,
                                     min_duration=duration)
        if not slots:
            flash(f'No availability slot of at least {duration} minutes found in the next {days_ahead} days. '
                  'Add a longer availability slot or increase days ahead.', 'warning')
            return redirect(url_for('availability.auto_schedule_picker'))
        slot = slots[0]
        proposal['items'].append({
            'student_ids': [s.id for s in students],
            'student_names': [s.display_name for s in students],
            'date': slot['date'], 'day_name': slot['day_name'],
            'start_time': slot['start_time'], 'end_time': slot['end_time'],
            'display': slot['display'],
        })

    session['auto_proposal'] = proposal
    return render_template('availability/auto_review.html', proposal=proposal)


@availability_bp.route('/auto/remove', methods=['POST'])
@login_required
def auto_schedule_remove():
    """Remove an item or attendee from the session proposal (XHR)."""
    proposal = session.get('auto_proposal')
    if not proposal:
        return jsonify({'error': 'No proposal in session.'}), 400

    data = request.get_json(silent=True) or {}
    if proposal['mode'] == 'individual':
        idx = data.get('index')
        if idx is None or not isinstance(idx, int) or idx < 0 or idx >= len(proposal['items']):
            return jsonify({'error': 'Invalid index.'}), 400
        proposal['items'].pop(idx)
    else:  # group
        sid = data.get('student_id')
        if sid is None or not proposal['items']:
            return jsonify({'error': 'Invalid student.'}), 400
        item = proposal['items'][0]
        try:
            i = item['student_ids'].index(int(sid))
            item['student_ids'].pop(i)
            item['student_names'].pop(i)
        except (ValueError, TypeError):
            return jsonify({'error': 'Student not in group.'}), 400
        if not item['student_ids']:
            proposal['items'] = []

    session['auto_proposal'] = proposal
    session.modified = True
    return jsonify({'ok': True, 'remaining': len(proposal['items'])})


@availability_bp.route('/auto/confirm', methods=['POST'])
@login_required
def auto_schedule_confirm():
    """Commit the session proposal to the database."""
    proposal = session.get('auto_proposal')
    if not proposal or not proposal.get('items'):
        flash('No proposal to confirm. Start over.', 'warning')
        return redirect(url_for('availability.auto_schedule_picker'))

    mode = proposal['mode']
    notes = proposal.get('notes') or None
    meeting_type = proposal.get('meeting_type', 'general')
    title = proposal.get('title') or 'Check-in'
    scheduled = 0
    skipped_taken = 0
    created_booking_ids = []
    created_event_ids = []

    if mode == 'individual':
        for item in proposal['items']:
            student = Student.query.get(item['student_id'])
            if not student or student.assigned_counselor_id != current_user.id:
                skipped_taken += 1
                continue
            try:
                appt_date = datetime.strptime(item['date'], '%Y-%m-%d').date()
            except ValueError:
                skipped_taken += 1
                continue
            conflict = Booking.query.filter_by(
                counselor_id=current_user.id,
                appointment_date=appt_date,
                start_time=item['start_time'],
            ).filter(Booking.status != 'cancelled').first()
            if conflict:
                skipped_taken += 1
                continue
            b = Booking(
                counselor_id=current_user.id,
                student_id=student.id,
                booker_name=student.display_name,
                booker_relationship='counselor',
                student_name=student.display_name,
                meeting_type=meeting_type,
                notes=notes,
                appointment_date=appt_date,
                start_time=item['start_time'],
                end_time=item['end_time'],
                status='confirmed',
            )
            db.session.add(b)
            db.session.flush()
            log_action('auto_schedule.create', resource_type='booking',
                       resource_id=b.id,
                       details=f'individual cohort student={student.id} title={title}')
            created_booking_ids.append(b.id)
            scheduled += 1
    else:  # group
        item = proposal['items'][0]
        try:
            appt_date = datetime.strptime(item['date'], '%Y-%m-%d').date()
            start_dt = datetime.combine(appt_date,
                                        datetime.strptime(item['start_time'], '%H:%M').time())
            end_dt = datetime.combine(appt_date,
                                      datetime.strptime(item['end_time'], '%H:%M').time())
        except ValueError:
            flash('Invalid date/time in proposal.', 'danger')
            return redirect(url_for('availability.auto_schedule_picker'))

        attendee_lines = '\n'.join(f'  - {name}' for name in item['student_names'])
        description = f'Cohort meeting with {len(item["student_ids"])} students.\n\nAttendees:\n{attendee_lines}'
        if notes:
            description += f'\n\nNotes: {notes}'

        event = CalendarEvent(
            owner_id=current_user.id,
            title=title,
            description=description,
            start_datetime=start_dt,
            end_datetime=end_dt,
            event_type='group_session',
            color=CalendarEvent.EVENT_COLORS.get('group_session', '#F39C12'),
        )
        db.session.add(event)
        db.session.flush()
        log_action('auto_schedule.create', resource_type='calendar_event',
                   resource_id=event.id,
                   details=f'group cohort students={len(item["student_ids"])} title={title}')
        created_event_ids.append(event.id)
        scheduled = 1

        for sid in item['student_ids']:
            student = Student.query.get(sid)
            if not student or student.assigned_counselor_id != current_user.id:
                continue
            b = Booking(
                counselor_id=current_user.id,
                student_id=student.id,
                booker_name=student.display_name,
                booker_relationship='counselor',
                student_name=student.display_name,
                meeting_type=meeting_type,
                notes=f'(Part of group: {title}){chr(10)}{notes}' if notes else f'(Part of group: {title})',
                appointment_date=appt_date,
                start_time=item['start_time'],
                end_time=item['end_time'],
                status='confirmed',
            )
            db.session.add(b)
            db.session.flush()
            created_booking_ids.append(b.id)

    db.session.commit()

    session.pop('auto_proposal', None)
    session['last_auto_batch'] = {
        'booking_ids': created_booking_ids,
        'event_ids': created_event_ids,
        'created_at': datetime.now(timezone.utc).isoformat(),
    }

    if mode == 'individual':
        msg = f'{scheduled} appointment{"s" if scheduled != 1 else ""} scheduled'
    else:
        msg = f'Group meeting scheduled with {len(created_booking_ids)} student{"s" if len(created_booking_ids) != 1 else ""}'
    if skipped_taken:
        msg += f' ({skipped_taken} skipped — slot taken)'
    flash(msg + '.', 'success')
    return redirect(url_for('availability.index'))


@availability_bp.route('/auto/download.ics')
@login_required
def auto_schedule_download_ics():
    """Download just the most recently created batch as an .ics file."""
    batch = session.get('last_auto_batch')
    if not batch:
        flash('No recent batch to download. Try again after scheduling.', 'warning')
        return redirect(url_for('availability.index'))

    bookings = []
    events = []
    if batch.get('booking_ids'):
        bookings = (Booking.query
                    .filter(Booking.id.in_(batch['booking_ids']),
                            Booking.counselor_id == current_user.id)
                    .all())
    if batch.get('event_ids'):
        events = (CalendarEvent.query
                  .filter(CalendarEvent.id.in_(batch['event_ids']),
                          CalendarEvent.owner_id == current_user.id)
                  .all())

    ics = build_ical_feed(current_user, calendar_events=events, bookings=bookings,
                          calname_suffix='Cohort Batch')
    return Response(
        ics, mimetype='text/calendar',
        headers={'Content-Disposition': 'attachment; filename="cohort-batch.ics"'},
    )
