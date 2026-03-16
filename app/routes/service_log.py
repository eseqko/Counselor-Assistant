from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models.service_record import ServiceRecord
from app.models.student import Student
from app.utils.audit import log_action
from app.utils.helpers import parse_date
from datetime import date

service_log_bp = Blueprint('service_log', __name__)


@service_log_bp.route('/')
@login_required
def index():
    student_id = request.args.get('student_id', '')
    service_type = request.args.get('service_type', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    query = ServiceRecord.query.filter_by(counselor_id=current_user.id)

    if student_id:
        query = query.filter_by(student_id=int(student_id))
    if service_type:
        query = query.filter_by(service_type=service_type)
    if date_from:
        query = query.filter(ServiceRecord.date >= parse_date(date_from))
    if date_to:
        query = query.filter(ServiceRecord.date <= parse_date(date_to))

    records = query.order_by(ServiceRecord.date.desc()).all()
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active'
    ).order_by(Student.last_name).all()

    return render_template('service_log/index.html',
        records=records, students=students,
        student_id=student_id, service_type=service_type,
        service_types=ServiceRecord.SERVICE_TYPES)


@service_log_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_record():
    if request.method == 'POST':
        record = ServiceRecord(
            student_id=int(request.form['student_id']),
            counselor_id=current_user.id,
            date=parse_date(request.form.get('date')) or date.today(),
            service_type=request.form['service_type'],
            topic=request.form.get('topic', ''),
            description=request.form.get('description', ''),
            duration_minutes=int(request.form['duration_minutes']) if request.form.get('duration_minutes') else None,
            asca_domain=request.form.get('asca_domain', ''),
            delivery_method=request.form.get('delivery_method', ''),
            setting=request.form.get('setting', ''),
            outcome=request.form.get('outcome', ''),
            follow_up_required='follow_up_required' in request.form,
            follow_up_date=parse_date(request.form.get('follow_up_date')),
            referral_made='referral_made' in request.form,
            referral_to=request.form.get('referral_to', ''),
        )
        db.session.add(record)
        db.session.commit()
        log_action('create', 'service_record', record.id)
        flash('Service record added.', 'success')
        return redirect(url_for('service_log.index'))

    student_id = request.args.get('student_id', '')
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active'
    ).order_by(Student.last_name).all()

    return render_template('service_log/add.html',
        students=students, preselected_student=student_id,
        service_types=ServiceRecord.SERVICE_TYPES)


@service_log_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_record(id):
    record = ServiceRecord.query.get_or_404(id)

    if request.method == 'POST':
        record.date = parse_date(request.form.get('date')) or record.date
        record.service_type = request.form['service_type']
        record.topic = request.form.get('topic', '')
        record.description = request.form.get('description', '')
        record.duration_minutes = int(request.form['duration_minutes']) if request.form.get('duration_minutes') else None
        record.asca_domain = request.form.get('asca_domain', '')
        record.delivery_method = request.form.get('delivery_method', '')
        record.setting = request.form.get('setting', '')
        record.outcome = request.form.get('outcome', '')
        record.follow_up_required = 'follow_up_required' in request.form
        record.follow_up_date = parse_date(request.form.get('follow_up_date'))
        record.referral_made = 'referral_made' in request.form
        record.referral_to = request.form.get('referral_to', '')

        db.session.commit()
        log_action('update', 'service_record', record.id)
        flash('Service record updated.', 'success')
        return redirect(url_for('service_log.index'))

    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active'
    ).order_by(Student.last_name).all()
    return render_template('service_log/edit.html', record=record,
        students=students, service_types=ServiceRecord.SERVICE_TYPES)


@service_log_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete_record(id):
    record = ServiceRecord.query.get_or_404(id)
    log_action('delete', 'service_record', record.id)
    db.session.delete(record)
    db.session.commit()
    flash('Service record deleted.', 'warning')
    return redirect(url_for('service_log.index'))
