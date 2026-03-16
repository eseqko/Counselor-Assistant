from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.calendar_event import CalendarEvent
from app.models.student import Student
from app.utils.audit import log_action
from datetime import datetime, date, timedelta

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

    return render_template('calendar/index.html',
        current_date=current_date, view=view,
        event_types=CalendarEvent.EVENT_TYPES,
        event_colors=CalendarEvent.EVENT_COLORS)


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
