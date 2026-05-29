from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from app import db
from app.models.note import Note
from app.models.student import Student
from app.models.calendar_event import CalendarEvent
from app.utils.audit import log_action
from app.utils.helpers import parse_date
from datetime import date, datetime, timedelta

notes_bp = Blueprint('notes', __name__)


def _create_follow_up_event(note):
    """Create a calendar event for a note's follow-up date."""
    if not note.follow_up_needed or not note.follow_up_date:
        return
    student = Student.query.get(note.student_id)
    student_name = student.display_name if student else 'Student'
    title = f"Follow-Up: {student_name}"
    if note.title:
        title += f" — {note.title}"

    start_dt = datetime.combine(note.follow_up_date, datetime.min.time().replace(hour=9))
    end_dt = start_dt + timedelta(minutes=30)

    event = CalendarEvent(
        owner_id=current_user.id,
        title=title,
        description=note.follow_up_notes or f"Follow-up from note: {note.title or note.note_type}",
        start_datetime=start_dt,
        end_datetime=end_dt,
        event_type='follow_up',
        color=CalendarEvent.EVENT_COLORS.get('follow_up', '#E91E63'),
        student_id=note.student_id,
        reminder_minutes=15,
    )
    db.session.add(event)
    return event


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

    page = request.args.get('page', 1, type=int)
    pagination = query.order_by(
        Note.session_date.desc(), Note.created_at.desc()
    ).paginate(page=max(1, page), per_page=50, error_out=False)
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active'
    ).order_by(Student.last_name).all()

    return render_template('notes/index.html',
        notes=pagination.items, pagination=pagination,
        search=search, note_type=note_type,
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
            private_comment=request.form.get('private_comment', ''),
            session_date=parse_date(request.form.get('session_date')) or date.today(),
            duration_minutes=int(request.form['duration_minutes']) if request.form.get('duration_minutes') else None,
            asca_domain=request.form.get('asca_domain', ''),
            topic_category=request.form.get('topic_category', ''),
            delivery_method=request.form.get('delivery_method', ''),
            setting=request.form.get('setting', ''),
            outcome=request.form.get('outcome', ''),
            referred_by=request.form.get('referred_by', ''),
            referral_made='referral_made' in request.form,
            referral_to=request.form.get('referral_to', ''),
            follow_up_needed='follow_up_needed' in request.form,
            follow_up_date=parse_date(request.form.get('follow_up_date')),
            follow_up_notes=request.form.get('follow_up_notes', ''),
            is_confidential='is_confidential' in request.form,
        )
        db.session.add(note)
        db.session.flush()
        event = _create_follow_up_event(note)
        db.session.commit()
        log_action('create', 'note', note.id, f'Note for student #{note.student_id}')
        if event:
            flash('Note added with follow-up reminder on your calendar.', 'success')
        else:
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
    if note.author_id != current_user.id:
        abort(403)
    log_action('view', 'note', note.id)
    return render_template('notes/view.html', note=note,
        note_types=Note.NOTE_TYPES)


@notes_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_note(id):
    note = Note.query.get_or_404(id)
    if note.author_id != current_user.id:
        abort(403)

    if request.method == 'POST':
        note.note_type = request.form['note_type']
        note.title = request.form.get('title', '')
        note.content = request.form['content']
        note.private_comment = request.form.get('private_comment', '')
        note.session_date = parse_date(request.form.get('session_date')) or note.session_date
        note.duration_minutes = int(request.form['duration_minutes']) if request.form.get('duration_minutes') else None
        note.asca_domain = request.form.get('asca_domain', '')
        note.topic_category = request.form.get('topic_category', '')
        note.delivery_method = request.form.get('delivery_method', '')
        note.setting = request.form.get('setting', '')
        note.outcome = request.form.get('outcome', '')
        note.referred_by = request.form.get('referred_by', '')
        note.referral_made = 'referral_made' in request.form
        note.referral_to = request.form.get('referral_to', '')
        old_follow_up_date = note.follow_up_date
        old_follow_up_needed = note.follow_up_needed

        note.follow_up_needed = 'follow_up_needed' in request.form
        note.follow_up_date = parse_date(request.form.get('follow_up_date'))
        note.follow_up_notes = request.form.get('follow_up_notes', '')
        note.is_confidential = 'is_confidential' in request.form

        event = None
        if note.follow_up_needed and note.follow_up_date:
            if not old_follow_up_needed or old_follow_up_date != note.follow_up_date:
                event = _create_follow_up_event(note)

        db.session.commit()
        log_action('update', 'note', note.id)
        if event:
            flash('Note updated with follow-up reminder on your calendar.', 'success')
        else:
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
    if note.author_id != current_user.id:
        abort(403)
    log_action('delete', 'note', note.id)
    db.session.delete(note)
    db.session.commit()
    flash('Note deleted.', 'warning')
    return redirect(url_for('notes.index'))


@notes_bp.route('/batch-delete', methods=['POST'])
@login_required
def batch_delete():
    """Delete multiple notes at once."""
    note_ids = request.form.getlist('note_ids')
    if not note_ids:
        flash('No notes selected.', 'warning')
        return redirect(url_for('notes.index'))

    try:
        ids = [int(nid) for nid in note_ids]
    except (ValueError, TypeError):
        flash('Invalid selection.', 'danger')
        return redirect(url_for('notes.index'))

    notes = Note.query.filter(
        Note.id.in_(ids),
        Note.author_id == current_user.id,
    ).all()
    count = len(notes)
    for note in notes:
        db.session.delete(note)
    db.session.commit()
    log_action('delete', 'note', details=f'Batch deleted {count} notes')
    flash(f'Deleted {count} notes.', 'warning')
    return redirect(url_for('notes.index'))
