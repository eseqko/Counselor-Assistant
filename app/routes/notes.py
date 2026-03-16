from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models.note import Note
from app.models.student import Student
from app.utils.audit import log_action
from app.utils.helpers import parse_date
from datetime import date

notes_bp = Blueprint('notes', __name__)


@notes_bp.route('/')
@login_required
def index():
    search = request.args.get('search', '').strip()
    note_type = request.args.get('type', '')
    student_id = request.args.get('student_id', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    query = Note.query.filter_by(author_id=current_user.id)

    if note_type:
        query = query.filter_by(note_type=note_type)
    if student_id:
        query = query.filter_by(student_id=int(student_id))
    if search:
        query = query.filter(
            db.or_(
                Note.title.ilike(f'%{search}%'),
                Note.content.ilike(f'%{search}%'),
            )
        )
    if date_from:
        query = query.filter(Note.session_date >= parse_date(date_from))
    if date_to:
        query = query.filter(Note.session_date <= parse_date(date_to))

    notes = query.order_by(Note.session_date.desc(), Note.created_at.desc()).all()
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active'
    ).order_by(Student.last_name).all()

    return render_template('notes/index.html',
        notes=notes, search=search, note_type=note_type,
        student_id=student_id, students=students,
        note_types=Note.NOTE_TYPES)


@notes_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_note():
    if request.method == 'POST':
        note = Note(
            student_id=int(request.form['student_id']),
            author_id=current_user.id,
            note_type=request.form['note_type'],
            title=request.form.get('title', ''),
            content=request.form['content'],
            session_date=parse_date(request.form.get('session_date')) or date.today(),
            duration_minutes=int(request.form['duration_minutes']) if request.form.get('duration_minutes') else None,
            asca_domain=request.form.get('asca_domain', ''),
            topic_category=request.form.get('topic_category', ''),
            delivery_method=request.form.get('delivery_method', ''),
            follow_up_needed='follow_up_needed' in request.form,
            follow_up_date=parse_date(request.form.get('follow_up_date')),
            follow_up_notes=request.form.get('follow_up_notes', ''),
            is_confidential='is_confidential' in request.form,
        )
        db.session.add(note)
        db.session.commit()
        log_action('create', 'note', note.id, f'Note for student #{note.student_id}')
        flash('Note added successfully.', 'success')
        return redirect(url_for('notes.index'))

    student_id = request.args.get('student_id', '')
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active'
    ).order_by(Student.last_name).all()

    return render_template('notes/add.html',
        students=students, preselected_student=student_id,
        note_types=Note.NOTE_TYPES,
        asca_domains=Note.ASCA_DOMAINS,
        delivery_methods=Note.DELIVERY_METHODS)


@notes_bp.route('/<int:id>')
@login_required
def view_note(id):
    note = Note.query.get_or_404(id)
    log_action('view', 'note', note.id)
    return render_template('notes/view.html', note=note)


@notes_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_note(id):
    note = Note.query.get_or_404(id)

    if request.method == 'POST':
        note.note_type = request.form['note_type']
        note.title = request.form.get('title', '')
        note.content = request.form['content']
        note.session_date = parse_date(request.form.get('session_date')) or note.session_date
        note.duration_minutes = int(request.form['duration_minutes']) if request.form.get('duration_minutes') else None
        note.asca_domain = request.form.get('asca_domain', '')
        note.topic_category = request.form.get('topic_category', '')
        note.delivery_method = request.form.get('delivery_method', '')
        note.follow_up_needed = 'follow_up_needed' in request.form
        note.follow_up_date = parse_date(request.form.get('follow_up_date'))
        note.follow_up_notes = request.form.get('follow_up_notes', '')
        note.is_confidential = 'is_confidential' in request.form

        db.session.commit()
        log_action('update', 'note', note.id)
        flash('Note updated.', 'success')
        return redirect(url_for('notes.view_note', id=note.id))

    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active'
    ).order_by(Student.last_name).all()
    return render_template('notes/edit.html', note=note, students=students,
        note_types=Note.NOTE_TYPES, asca_domains=Note.ASCA_DOMAINS,
        delivery_methods=Note.DELIVERY_METHODS)


@notes_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete_note(id):
    note = Note.query.get_or_404(id)
    log_action('delete', 'note', note.id)
    db.session.delete(note)
    db.session.commit()
    flash('Note deleted.', 'warning')
    return redirect(url_for('notes.index'))
