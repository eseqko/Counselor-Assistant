from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models.activity import Activity
from app.utils.audit import log_action
from app.utils.helpers import parse_date, parse_time
from app.utils.roles import owned_or_404
from datetime import date, datetime

activity_log_bp = Blueprint('activity_log', __name__)


@activity_log_bp.route('/')
@login_required
def index():
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    service_type = request.args.get('service_type', '')

    query = Activity.query.filter_by(counselor_id=current_user.id)

    if service_type:
        query = query.filter_by(service_type=service_type)
    if date_from:
        query = query.filter(Activity.date >= parse_date(date_from))
    if date_to:
        query = query.filter(Activity.date <= parse_date(date_to))

    activities = query.order_by(Activity.date.desc(), Activity.start_time.desc()).all()

    return render_template('activity_log/index.html',
        activities=activities, date_from=date_from, date_to=date_to,
        service_type=service_type, service_types=Activity.SERVICE_TYPES)


@activity_log_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_activity():
    if request.method == 'POST':
        start_time = parse_time(request.form.get('start_time'))
        end_time = parse_time(request.form.get('end_time'))

        # Calculate duration
        duration = None
        if start_time and end_time:
            start_dt = datetime.combine(date.today(), start_time)
            end_dt = datetime.combine(date.today(), end_time)
            duration = int((end_dt - start_dt).total_seconds() / 60)
        elif request.form.get('duration_minutes'):
            duration = int(request.form['duration_minutes'])

        activity = Activity(
            counselor_id=current_user.id,
            title=request.form['title'],
            description=request.form.get('description', ''),
            date=parse_date(request.form.get('date')) or date.today(),
            start_time=start_time,
            end_time=end_time,
            duration_minutes=duration,
            service_type=request.form['service_type'],
            category=request.form.get('category', ''),
            topic=request.form.get('topic', ''),
            delivery_type=request.form.get('delivery_type', ''),
            num_students=int(request.form.get('num_students', 0)),
            grade_levels=request.form.get('grade_levels', ''),
        )
        db.session.add(activity)
        db.session.commit()
        log_action('create', 'activity', activity.id)
        flash('Activity logged.', 'success')
        return redirect(url_for('activity_log.index'))

    return render_template('activity_log/add.html',
        service_types=Activity.SERVICE_TYPES,
        categories=Activity.CATEGORIES)


@activity_log_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_activity(id):
    activity = owned_or_404(Activity, id)

    if request.method == 'POST':
        activity.title = request.form['title']
        activity.description = request.form.get('description', '')
        activity.date = parse_date(request.form.get('date')) or activity.date
        activity.start_time = parse_time(request.form.get('start_time'))
        activity.end_time = parse_time(request.form.get('end_time'))
        activity.service_type = request.form['service_type']
        activity.category = request.form.get('category', '')
        activity.topic = request.form.get('topic', '')
        activity.delivery_type = request.form.get('delivery_type', '')
        activity.num_students = int(request.form.get('num_students', 0))

        if activity.start_time and activity.end_time:
            start_dt = datetime.combine(date.today(), activity.start_time)
            end_dt = datetime.combine(date.today(), activity.end_time)
            activity.duration_minutes = int((end_dt - start_dt).total_seconds() / 60)

        db.session.commit()
        log_action('update', 'activity', activity.id)
        flash('Activity updated.', 'success')
        return redirect(url_for('activity_log.index'))

    return render_template('activity_log/edit.html', activity=activity,
        service_types=Activity.SERVICE_TYPES, categories=Activity.CATEGORIES)


@activity_log_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete_activity(id):
    activity = owned_or_404(Activity, id)
    log_action('delete', 'activity', activity.id)
    db.session.delete(activity)
    db.session.commit()
    flash('Activity removed.', 'warning')
    return redirect(url_for('activity_log.index'))
