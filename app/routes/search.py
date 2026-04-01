"""Global instant search across students, notes, and meeting notes."""
from flask import Blueprint, request, jsonify, url_for
from flask_login import login_required, current_user
from app import db, csrf
from app.models.student import Student
from app.models.note import Note
from app.models.meeting_note import MeetingNote

search_bp = Blueprint('search', __name__)


@search_bp.route('/api/search')
@login_required
def instant_search():
    """Return categorized results for the global search bar."""
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify({'results': []})

    like = f'%{q}%'
    results = []

    # ── Students ──
    students = Student.query.filter(
        Student.assigned_counselor_id == current_user.id,
        db.or_(
            Student.first_name.ilike(like),
            Student.last_name.ilike(like),
            Student.student_id_number.ilike(like),
            (Student.first_name + ' ' + Student.last_name).ilike(like),
        )
    ).order_by(Student.last_name).limit(5).all()

    for s in students:
        results.append({
            'type': 'student',
            'icon': '&#128100;',
            'title': f'{s.first_name} {s.last_name}',
            'subtitle': f'Grade {s.grade_level} &middot; ID: {s.student_id_number}',
            'url': url_for('caseload.view_student', id=s.id),
        })

    # ── Counselor Notes ──
    notes = Note.query.filter(
        Note.author_id == current_user.id,
        db.or_(
            Note.title.ilike(like),
            Note.content.ilike(like),
        )
    ).order_by(Note.session_date.desc()).limit(5).all()

    for n in notes:
        # Truncate content for preview
        preview = (n.title or n.content[:60] or 'Untitled note')
        student = Student.query.get(n.student_id)
        sub = ''
        if student:
            sub = f'{student.first_name} {student.last_name}'
        if n.session_date:
            sub += f' &middot; {n.session_date.strftime("%b %d, %Y")}' if sub else n.session_date.strftime('%b %d, %Y')
        results.append({
            'type': 'note',
            'icon': '&#128221;',
            'title': preview[:80],
            'subtitle': sub,
            'url': url_for('notes.view_note', id=n.id),
        })

    # ── Meeting Notes ──
    meetings = MeetingNote.query.filter(
        MeetingNote.author_id == current_user.id,
        db.or_(
            MeetingNote.title.ilike(like),
            MeetingNote.content.ilike(like),
        )
    ).order_by(MeetingNote.meeting_date.desc()).limit(5).all()

    for m in meetings:
        sub = m.meeting_type.replace('_', ' ').title() if m.meeting_type else ''
        if m.meeting_date:
            sub += f' &middot; {m.meeting_date.strftime("%b %d, %Y")}' if sub else m.meeting_date.strftime('%b %d, %Y')
        results.append({
            'type': 'meeting',
            'icon': '&#128197;',
            'title': m.title[:80],
            'subtitle': sub,
            'url': url_for('meeting_notes.view', note_id=m.id),
        })

    return jsonify({'results': results})
