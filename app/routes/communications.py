from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models.communication import CommunicationLog
from app.models.student import Student
from app.utils.audit import log_action
from app.utils.helpers import parse_date
from app.utils.roles import owned_or_404

communications_bp = Blueprint('communications', __name__)


@communications_bp.route('/')
@login_required
def index():
    student_id = request.args.get('student_id', '')
    contact_type = request.args.get('contact_type', '')

    query = CommunicationLog.query.filter_by(counselor_id=current_user.id)
    if student_id:
        query = query.filter_by(student_id=int(student_id))
    if contact_type:
        query = query.filter_by(contact_type=contact_type)

    page = request.args.get('page', 1, type=int)
    pagination = query.order_by(
        CommunicationLog.contact_date.desc(),
        CommunicationLog.created_at.desc()
    ).paginate(page=max(1, page), per_page=50, error_out=False)
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active'
    ).order_by(Student.last_name).all()

    return render_template('communications/index.html',
        logs=pagination.items, pagination=pagination, students=students,
        student_id=student_id, contact_type=contact_type,
        contact_types=CommunicationLog.CONTACT_TYPES)


@communications_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if request.method == 'POST':
        log = CommunicationLog(
            student_id=int(request.form['student_id']) if request.form.get('student_id') else None,
            counselor_id=current_user.id,
            contact_date=parse_date(request.form.get('contact_date')) or date.today(),
            contact_type=request.form['contact_type'],
            direction=request.form.get('direction', 'outgoing'),
            contact_person=request.form['contact_person'].strip(),
            contact_role=request.form.get('contact_role', ''),
            contact_email=request.form.get('contact_email', '').strip(),
            contact_phone=request.form.get('contact_phone', '').strip(),
            subject=request.form.get('subject', '').strip(),
            summary=request.form.get('summary', '').strip(),
            duration_minutes=int(request.form['duration_minutes']) if request.form.get('duration_minutes') else None,
            follow_up_needed='follow_up_needed' in request.form,
            follow_up_date=parse_date(request.form.get('follow_up_date')),
            follow_up_notes=request.form.get('follow_up_notes', '').strip(),
        )
        db.session.add(log)
        db.session.commit()
        log_action('create', 'communication', log.id,
                   f'Logged {log.contact_type} with {log.contact_person}')
        flash('Communication logged.', 'success')
        return redirect(url_for('communications.index'))

    student_id = request.args.get('student_id', '')
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active'
    ).order_by(Student.last_name).all()

    # Pre-fill from query params (e.g. from email drafts)
    prefill = {
        'subject': request.args.get('subject', ''),
        'contact_person': request.args.get('contact_person', ''),
        'contact_email': request.args.get('contact_email', ''),
        'contact_type': request.args.get('contact_type', ''),
        'summary': request.args.get('summary', ''),
    }

    return render_template('communications/add.html',
        students=students, preselected_student=student_id,
        contact_types=CommunicationLog.CONTACT_TYPES,
        directions=CommunicationLog.DIRECTIONS,
        contact_roles=CommunicationLog.CONTACT_ROLES,
        prefill=prefill)


@communications_bp.route('/<int:id>')
@login_required
def view(id):
    log = owned_or_404(CommunicationLog, id)
    log_action('view', 'communication', log.id)
    return render_template('communications/view.html', log=log)


@communications_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    log = owned_or_404(CommunicationLog, id)
    if request.method == 'POST':
        log.contact_date = parse_date(request.form.get('contact_date')) or log.contact_date
        log.contact_type = request.form['contact_type']
        log.direction = request.form.get('direction', 'outgoing')
        log.contact_person = request.form['contact_person'].strip()
        log.contact_role = request.form.get('contact_role', '')
        log.contact_email = request.form.get('contact_email', '').strip()
        log.contact_phone = request.form.get('contact_phone', '').strip()
        log.subject = request.form.get('subject', '').strip()
        log.summary = request.form.get('summary', '').strip()
        log.duration_minutes = int(request.form['duration_minutes']) if request.form.get('duration_minutes') else None
        log.follow_up_needed = 'follow_up_needed' in request.form
        log.follow_up_date = parse_date(request.form.get('follow_up_date'))
        log.follow_up_notes = request.form.get('follow_up_notes', '').strip()
        log.follow_up_completed = 'follow_up_completed' in request.form
        db.session.commit()
        log_action('update', 'communication', log.id)
        flash('Communication updated.', 'success')
        return redirect(url_for('communications.view', id=log.id))

    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id
    ).order_by(Student.last_name).all()
    return render_template('communications/edit.html', log=log,
        students=students,
        contact_types=CommunicationLog.CONTACT_TYPES,
        directions=CommunicationLog.DIRECTIONS,
        contact_roles=CommunicationLog.CONTACT_ROLES)


@communications_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    log = owned_or_404(CommunicationLog, id)
    log_action('delete', 'communication', log.id)
    db.session.delete(log)
    db.session.commit()
    flash('Communication deleted.', 'warning')
    return redirect(url_for('communications.index'))
