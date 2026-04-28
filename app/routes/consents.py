import os
from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models.consent import ConsentRecord
from app.models.student import Student
from app.utils.audit import log_action
from app.utils.helpers import parse_date

consents_bp = Blueprint('consents', __name__)

ALLOWED_EXT = {'pdf', 'png', 'jpg', 'jpeg', 'doc', 'docx'}


def _consent_dir():
    folder = os.path.join(current_app.config.get('UPLOAD_FOLDER', 'data/uploads'), 'consents')
    os.makedirs(folder, exist_ok=True)
    return folder


@consents_bp.route('/')
@login_required
def index():
    student_id = request.args.get('student_id', '')
    status = request.args.get('status', '')
    consent_type = request.args.get('consent_type', '')

    query = ConsentRecord.query.filter_by(counselor_id=current_user.id)
    if student_id:
        query = query.filter_by(student_id=int(student_id))
    if status:
        query = query.filter_by(status=status)
    if consent_type:
        query = query.filter_by(consent_type=consent_type)

    consents = query.order_by(ConsentRecord.created_at.desc()).all()
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active'
    ).order_by(Student.last_name).all()

    return render_template('consents/index.html',
        consents=consents, students=students,
        student_id=student_id, status=status, consent_type=consent_type,
        consent_types=ConsentRecord.CONSENT_TYPES,
        statuses=ConsentRecord.STATUSES)


@consents_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if request.method == 'POST':
        consent = ConsentRecord(
            student_id=int(request.form['student_id']),
            counselor_id=current_user.id,
            consent_type=request.form['consent_type'],
            description=request.form.get('description', '').strip(),
            guardian_name=request.form.get('guardian_name', '').strip(),
            guardian_relationship=request.form.get('guardian_relationship', ''),
            guardian_phone=request.form.get('guardian_phone', '').strip(),
            guardian_email=request.form.get('guardian_email', '').strip(),
            request_date=parse_date(request.form.get('request_date')) or date.today(),
            received_date=parse_date(request.form.get('received_date')),
            expiration_date=parse_date(request.form.get('expiration_date')),
            status=request.form.get('status', 'requested'),
            method=request.form.get('method', ''),
            notes=request.form.get('notes', '').strip(),
        )
        db.session.add(consent)
        db.session.flush()

        file = request.files.get('document')
        if file and file.filename:
            ext = file.filename.rsplit('.', 1)[-1].lower()
            if ext in ALLOWED_EXT:
                fname = secure_filename(f'consent_{consent.id}_{file.filename}')
                file.save(os.path.join(_consent_dir(), fname))
                consent.document_filename = fname

        db.session.commit()
        log_action('create', 'consent', consent.id,
                   f'Consent created: {consent.consent_type_label}')
        flash('Consent record created.', 'success')
        return redirect(url_for('consents.view', id=consent.id))

    student_id = request.args.get('student_id', '')
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active'
    ).order_by(Student.last_name).all()
    return render_template('consents/add.html',
        students=students, preselected_student=student_id,
        consent_types=ConsentRecord.CONSENT_TYPES,
        statuses=ConsentRecord.STATUSES,
        methods=ConsentRecord.METHODS,
        relationships=ConsentRecord.GUARDIAN_RELATIONSHIPS)


@consents_bp.route('/<int:id>')
@login_required
def view(id):
    consent = ConsentRecord.query.get_or_404(id)
    log_action('view', 'consent', consent.id)
    return render_template('consents/view.html', consent=consent)


@consents_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    consent = ConsentRecord.query.get_or_404(id)
    if request.method == 'POST':
        consent.consent_type = request.form['consent_type']
        consent.description = request.form.get('description', '').strip()
        consent.guardian_name = request.form.get('guardian_name', '').strip()
        consent.guardian_relationship = request.form.get('guardian_relationship', '')
        consent.guardian_phone = request.form.get('guardian_phone', '').strip()
        consent.guardian_email = request.form.get('guardian_email', '').strip()
        consent.request_date = parse_date(request.form.get('request_date'))
        consent.received_date = parse_date(request.form.get('received_date'))
        consent.expiration_date = parse_date(request.form.get('expiration_date'))
        consent.status = request.form.get('status', consent.status)
        consent.method = request.form.get('method', '')
        consent.notes = request.form.get('notes', '').strip()

        file = request.files.get('document')
        if file and file.filename:
            ext = file.filename.rsplit('.', 1)[-1].lower()
            if ext in ALLOWED_EXT:
                fname = secure_filename(f'consent_{consent.id}_{file.filename}')
                file.save(os.path.join(_consent_dir(), fname))
                consent.document_filename = fname

        db.session.commit()
        log_action('update', 'consent', consent.id)
        flash('Consent updated.', 'success')
        return redirect(url_for('consents.view', id=consent.id))

    return render_template('consents/edit.html', consent=consent,
        consent_types=ConsentRecord.CONSENT_TYPES,
        statuses=ConsentRecord.STATUSES,
        methods=ConsentRecord.METHODS,
        relationships=ConsentRecord.GUARDIAN_RELATIONSHIPS)


@consents_bp.route('/<int:id>/document')
@login_required
def download_document(id):
    consent = ConsentRecord.query.get_or_404(id)
    if not consent.document_filename:
        flash('No document on file.', 'warning')
        return redirect(url_for('consents.view', id=id))
    log_action('view', 'consent_document', consent.id)
    return send_file(os.path.join(_consent_dir(), consent.document_filename),
                     as_attachment=True)


@consents_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    consent = ConsentRecord.query.get_or_404(id)
    log_action('delete', 'consent', consent.id)
    if consent.document_filename:
        try:
            os.remove(os.path.join(_consent_dir(), consent.document_filename))
        except OSError:
            pass
    db.session.delete(consent)
    db.session.commit()
    flash('Consent record deleted.', 'warning')
    return redirect(url_for('consents.index'))
