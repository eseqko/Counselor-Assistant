"""Meeting Notes routes -- live note-taking with @student mentions."""
import re
from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from markupsafe import escape
from app import db
from app.models.meeting_note import MeetingNote, meeting_note_students
from app.models.student import Student
from app.utils.audit import log_action

meeting_notes_bp = Blueprint('meeting_notes', __name__,
                             template_folder='../templates/meeting_notes')

MEETING_TYPES = [
    ('general', 'General'),
    ('sst', 'SST'),
    ('parent_conference', 'Parent Conference'),
    ('iep_review', 'IEP Review'),
    ('504_review', '504 Review'),
    ('department', 'Department Meeting'),
    ('staff', 'Staff Meeting'),
    ('counselor_team', 'Counselor Team'),
    ('admin', 'Admin Meeting'),
    ('grade_level', 'Grade Level Team'),
    ('other', 'Other'),
]


def _render_content_html(raw_content):
    """Convert @[Student Name](id) and #hashtags into styled HTML."""
    def replace_mention(m):
        name = escape(m.group(1))
        sid = m.group(2)
        return (f'<a href="/caseload/{sid}" class="mention-chip" '
                f'data-student-id="{sid}">{name}</a>')

    TAG_COLORS = {
        'action': ('#dc2626', '#fef2f2'),
        'decision': ('#7c3aed', '#f5f3ff'),
        'followup': ('#d97706', '#fffbeb'),
        'question': ('#2563eb', '#eff6ff'),
        'idea': ('#059669', '#ecfdf5'),
        'concern': ('#e11d48', '#fff1f2'),
        'update': ('#0891b2', '#ecfeff'),
        'win': ('#16a34a', '#f0fdf4'),
    }

    def replace_tag(m):
        tag = m.group(1).lower()
        colors = TAG_COLORS.get(tag, ('#6b7280', '#f3f4f6'))
        return (f'<span class="note-tag" style="color:{colors[0]};background:{colors[1]}">'
                f'#{tag}</span>')

    html = str(escape(raw_content))
    # @mentions
    html = re.sub(r'@\[([^\]]+)\]\((\d+)\)', replace_mention, html)
    # #hashtags (only known ones get colored, rest get neutral)
    html = re.sub(r'#(action|decision|followup|question|idea|concern|update|win)\b',
                  replace_tag, html, flags=re.IGNORECASE)
    # Newlines
    html = html.replace('\n', '<br>')
    return html


def _extract_student_ids(raw_content):
    """Pull all student IDs from @[Name](id) markers."""
    return [int(sid) for sid in re.findall(r'@\[[^\]]+\]\((\d+)\)', raw_content)]


@meeting_notes_bp.route('/')
@login_required
def index():
    q = request.args.get('q', '').strip()
    mtype = request.args.get('type', '')
    student_id = request.args.get('student_id', '', type=str)

    query = MeetingNote.query.filter_by(author_id=current_user.id)

    if q:
        like = f'%{q}%'
        query = query.filter(
            db.or_(MeetingNote.title.ilike(like), MeetingNote.content.ilike(like))
        )
    if mtype:
        query = query.filter_by(meeting_type=mtype)
    if student_id:
        query = query.filter(MeetingNote.students.any(Student.id == int(student_id)))

    notes = query.order_by(MeetingNote.meeting_date.desc(), MeetingNote.created_at.desc()).all()
    students = (Student.query
                .filter_by(assigned_counselor_id=current_user.id, status='active')
                .order_by(Student.last_name).all())

    return render_template('meeting_notes/index.html',
                           notes=notes, students=students,
                           meeting_types=MEETING_TYPES,
                           q=q, mtype=mtype, student_id=student_id)


@meeting_notes_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if request.method == 'POST':
        raw_content = request.form.get('content', '').strip()
        title = request.form.get('title', '').strip()
        if not title or not raw_content:
            flash('Title and content are required.', 'danger')
            return redirect(url_for('meeting_notes.add'))

        note = MeetingNote(
            author_id=current_user.id,
            title=title,
            content=raw_content,
            content_html=_render_content_html(raw_content),
            meeting_type=request.form.get('meeting_type', 'general'),
            meeting_date=_parse_date(request.form.get('meeting_date')) or date.today(),
            duration_minutes=_int_or_none(request.form.get('duration_minutes')),
            location=request.form.get('location', '').strip() or None,
            attendees=request.form.get('attendees', '').strip() or None,
            action_items=request.form.get('action_items', '').strip() or None,
            is_confidential='is_confidential' in request.form,
        )

        # Link mentioned students
        student_ids = _extract_student_ids(raw_content)
        if student_ids:
            students = Student.query.filter(Student.id.in_(student_ids)).all()
            note.students = students

        db.session.add(note)
        db.session.commit()
        log_action('create', 'meeting_note', note.id)
        flash('Meeting note saved.', 'success')
        return redirect(url_for('meeting_notes.view', note_id=note.id))

    students = (Student.query
                .filter_by(assigned_counselor_id=current_user.id, status='active')
                .order_by(Student.last_name).all())

    return render_template('meeting_notes/edit.html',
                           note=None, students=students,
                           meeting_types=MEETING_TYPES, today=date.today())


@meeting_notes_bp.route('/<int:note_id>')
@login_required
def view(note_id):
    note = MeetingNote.query.get_or_404(note_id)
    if note.author_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('meeting_notes.index'))
    log_action('view', 'meeting_note', note.id)

    type_label = dict(MEETING_TYPES).get(note.meeting_type, note.meeting_type)
    return render_template('meeting_notes/view.html', note=note, type_label=type_label)


@meeting_notes_bp.route('/<int:note_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(note_id):
    note = MeetingNote.query.get_or_404(note_id)
    if note.author_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('meeting_notes.index'))

    if request.method == 'POST':
        raw_content = request.form.get('content', '').strip()
        title = request.form.get('title', '').strip()
        if not title or not raw_content:
            flash('Title and content are required.', 'danger')
            return redirect(url_for('meeting_notes.edit', note_id=note_id))

        note.title = title
        note.content = raw_content
        note.content_html = _render_content_html(raw_content)
        note.meeting_type = request.form.get('meeting_type', 'general')
        note.meeting_date = _parse_date(request.form.get('meeting_date')) or note.meeting_date
        note.duration_minutes = _int_or_none(request.form.get('duration_minutes'))
        note.location = request.form.get('location', '').strip() or None
        note.attendees = request.form.get('attendees', '').strip() or None
        note.action_items = request.form.get('action_items', '').strip() or None
        note.is_confidential = 'is_confidential' in request.form

        # Re-link students from content
        student_ids = _extract_student_ids(raw_content)
        note.students = Student.query.filter(Student.id.in_(student_ids)).all() if student_ids else []

        db.session.commit()
        log_action('update', 'meeting_note', note.id)
        flash('Meeting note updated.', 'success')
        return redirect(url_for('meeting_notes.view', note_id=note.id))

    students = (Student.query
                .filter_by(assigned_counselor_id=current_user.id, status='active')
                .order_by(Student.last_name).all())
    return render_template('meeting_notes/edit.html',
                           note=note, students=students,
                           meeting_types=MEETING_TYPES, today=date.today())


@meeting_notes_bp.route('/<int:note_id>/delete', methods=['POST'])
@login_required
def delete(note_id):
    note = MeetingNote.query.get_or_404(note_id)
    if note.author_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('meeting_notes.index'))
    log_action('delete', 'meeting_note', note.id)
    db.session.delete(note)
    db.session.commit()
    flash('Meeting note deleted.', 'success')
    return redirect(url_for('meeting_notes.index'))


# ---------- API ----------

@meeting_notes_bp.route('/api/students')
@login_required
def api_students():
    """Search students for @mention autocomplete."""
    q = request.args.get('q', '').strip()
    query = Student.query.filter_by(assigned_counselor_id=current_user.id, status='active')
    if q:
        like = f'%{q}%'
        query = query.filter(
            db.or_(
                Student.first_name.ilike(like),
                Student.last_name.ilike(like),
                Student.student_id_number.ilike(like),
                (Student.first_name + ' ' + Student.last_name).ilike(like),
            )
        )
    students = query.order_by(Student.last_name).limit(15).all()
    return jsonify([{
        'id': s.id,
        'name': f'{s.first_name} {s.last_name}',
        'grade': s.grade_level,
        'sid': s.student_id_number,
        'iep': s.iep_status,
        'five04': getattr(s, 'plan_504_status', False),
    } for s in students])


# ---------- helpers ----------

def _parse_date(val):
    if not val:
        return None
    try:
        from datetime import datetime
        return datetime.strptime(val, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def _int_or_none(val):
    try:
        return int(val) if val else None
    except (ValueError, TypeError):
        return None
