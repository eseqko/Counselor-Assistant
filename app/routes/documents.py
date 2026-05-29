import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, current_app, abort
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models.document import StudentDocument
from app.models.student import Student
from app.utils.audit import log_action
from app.utils.helpers import parse_date

documents_bp = Blueprint('documents', __name__)

ALLOWED_EXT = {'pdf', 'png', 'jpg', 'jpeg', 'doc', 'docx', 'txt', 'xlsx', 'xls'}


def _docs_dir():
    folder = os.path.join(current_app.config.get('UPLOAD_FOLDER', 'data/uploads'), 'student_docs')
    os.makedirs(folder, exist_ok=True)
    return folder


@documents_bp.route('/')
@login_required
def index():
    student_id = request.args.get('student_id', '')
    document_type = request.args.get('document_type', '')

    query = StudentDocument.query.filter_by(counselor_id=current_user.id)
    if student_id:
        query = query.filter_by(student_id=int(student_id))
    if document_type:
        query = query.filter_by(document_type=document_type)

    docs = query.order_by(StudentDocument.uploaded_at.desc()).all()
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active'
    ).order_by(Student.last_name).all()

    return render_template('documents/index.html',
        documents=docs, students=students,
        student_id=student_id, document_type=document_type,
        document_types=StudentDocument.DOCUMENT_TYPES)


@documents_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if request.method == 'POST':
        file = request.files.get('file')
        if not file or not file.filename:
            flash('Please select a file.', 'danger')
            return redirect(url_for('documents.add'))

        ext = file.filename.rsplit('.', 1)[-1].lower()
        if ext not in ALLOWED_EXT:
            flash(f'File type .{ext} not allowed.', 'danger')
            return redirect(url_for('documents.add'))

        doc = StudentDocument(
            student_id=int(request.form['student_id']),
            counselor_id=current_user.id,
            document_type=request.form['document_type'],
            title=request.form['title'].strip(),
            description=request.form.get('description', '').strip(),
            original_filename=file.filename,
            mime_type=file.mimetype or '',
            document_date=parse_date(request.form.get('document_date')),
            expiration_date=parse_date(request.form.get('expiration_date')),
            is_confidential='is_confidential' in request.form,
            tags=request.form.get('tags', '').strip(),
            filename='',
        )
        db.session.add(doc)
        db.session.flush()

        fname = secure_filename(f'doc_{doc.id}_{file.filename}')
        path = os.path.join(_docs_dir(), fname)
        file.save(path)
        doc.filename = fname
        try:
            doc.file_size = os.path.getsize(path)
        except OSError:
            doc.file_size = None

        db.session.commit()
        log_action('create', 'student_document', doc.id, f'Uploaded: {doc.title}')
        flash('Document uploaded.', 'success')
        return redirect(url_for('documents.index', student_id=doc.student_id))

    student_id = request.args.get('student_id', '')
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active'
    ).order_by(Student.last_name).all()
    return render_template('documents/add.html',
        students=students, preselected_student=student_id,
        document_types=StudentDocument.DOCUMENT_TYPES)


@documents_bp.route('/<int:id>/download')
@login_required
def download(id):
    doc = StudentDocument.query.get_or_404(id)
    if doc.counselor_id != current_user.id:
        abort(403)
    log_action('download', 'student_document', doc.id)
    return send_file(os.path.join(_docs_dir(), doc.filename),
                     download_name=doc.original_filename or doc.filename,
                     as_attachment=True)


@documents_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    doc = StudentDocument.query.get_or_404(id)
    if doc.counselor_id != current_user.id:
        abort(403)
    log_action('delete', 'student_document', doc.id)
    try:
        os.remove(os.path.join(_docs_dir(), doc.filename))
    except OSError:
        pass
    student_id = doc.student_id
    db.session.delete(doc)
    db.session.commit()
    flash('Document deleted.', 'warning')
    return redirect(url_for('documents.index', student_id=student_id))
