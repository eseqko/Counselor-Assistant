"""Follow-Up Tracker — JSON-file-backed API for managing student follow-ups."""
import json
import os
import uuid
from datetime import datetime, date, timedelta, timezone
from flask import Blueprint, render_template, request, jsonify, url_for
from flask_login import login_required, current_user
from app import csrf

followups_bp = Blueprint('followups', __name__)

DATA_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', '..', 'data')
FOLLOWUPS_FILE = os.path.join(DATA_DIR, 'followups.json')


def _read_followups():
    """Read all follow-ups from JSON file."""
    if not os.path.exists(FOLLOWUPS_FILE):
        return []
    try:
        with open(FOLLOWUPS_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _write_followups(data):
    """Write follow-ups list to JSON file."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(FOLLOWUPS_FILE, 'w') as f:
        json.dump(data, f, indent=2, default=str)


def _get_user_followups():
    """Get follow-ups belonging to the current user."""
    all_fups = _read_followups()
    return [f for f in all_fups if f.get('counselor_id') == current_user.id]


def _save_user_followup(followup):
    """Save a single follow-up (insert or update) for the current user."""
    all_fups = _read_followups()
    idx = next((i for i, f in enumerate(all_fups) if f['id'] == followup['id']), None)
    if idx is not None:
        all_fups[idx] = followup
    else:
        all_fups.append(followup)
    _write_followups(all_fups)


def _delete_user_followup(followup_id):
    """Delete a follow-up by ID for the current user."""
    all_fups = _read_followups()
    all_fups = [f for f in all_fups
                if not (f['id'] == followup_id and f.get('counselor_id') == current_user.id)]
    _write_followups(all_fups)


# ── Page ──────────────────────────────────────────────────────────

@followups_bp.route('/')
@login_required
def index():
    """Render the Follow-Up Tracker page."""
    return render_template('followups/index.html')


@followups_bp.route('/digest')
@login_required
def digest():
    """Unified reminders inbox: every open follow-up (counseling notes +
    staff communications) grouped by Overdue / Today / This Week / Later,
    with one-click actions. Print-friendly so a counselor can take it with
    them — the right answer for a local/FERPA app instead of email."""
    from app.models.note import Note
    from app.models.communication import CommunicationLog
    from app import db as _db

    today = date.today()
    horizon = today + timedelta(days=30)

    note_q = Note.query.filter(
        Note.author_id == current_user.id,
        Note.follow_up_needed == True,
        _db.or_(Note.follow_up_completed == False, Note.follow_up_completed.is_(None)),
    ).order_by(Note.follow_up_date.asc().nullslast())
    notes = note_q.all()

    comm_q = CommunicationLog.query.filter(
        CommunicationLog.counselor_id == current_user.id,
        CommunicationLog.follow_up_needed == True,
        _db.or_(CommunicationLog.follow_up_completed == False,
                CommunicationLog.follow_up_completed.is_(None)),
    ).order_by(CommunicationLog.follow_up_date.asc().nullslast())
    comms = comm_q.all()

    items = []
    for n in notes:
        items.append({
            'kind': 'note',
            'id': n.id,
            'due': n.follow_up_date,
            'title': (n.title or n.note_type or 'Note'),
            'who': n.student.display_name if n.student else '(no student)',
            'who_url': (url_for('caseload.view_student', id=n.student_id)
                        if n.student_id else None),
            'detail': (n.follow_up_notes or '').strip(),
            'open_url': url_for('notes.view_note', id=n.id),
        })
    for c in comms:
        staff_name = c.staff.name if c.staff else c.contact_person
        items.append({
            'kind': 'staff',
            'id': c.id,
            'due': c.follow_up_date,
            'title': c.subject or c.type_label,
            'who': staff_name,
            'who_url': (url_for('staff.detail', staff_id=c.staff_id) + '#comms'
                        if c.staff_id else None),
            'detail': (c.follow_up_notes or '').strip(),
            'open_url': (url_for('staff.detail', staff_id=c.staff_id) + '#comms'
                         if c.staff_id else None),
        })

    overdue, due_today, this_week, later = [], [], [], []
    for it in items:
        d = it['due']
        if d is None:
            later.append(it)
        elif d < today:
            overdue.append(it)
        elif d == today:
            due_today.append(it)
        elif d <= today + timedelta(days=7):
            this_week.append(it)
        elif d <= horizon:
            later.append(it)
        # Anything past 30 days is hidden — won't surface in the digest.

    def _sort_key(it):
        return (it['due'] is None, it['due'] or date.max, it['title'].lower())
    for bucket in (overdue, due_today, this_week, later):
        bucket.sort(key=_sort_key)

    return render_template('followups/digest.html',
        today=today, overdue=overdue, due_today=due_today,
        this_week=this_week, later=later,
        total_open=len(items))


# ── JSON API ──────────────────────────────────────────────────────

@followups_bp.route('/api', methods=['GET'])
@login_required
def api_list():
    """Return all follow-ups for the current user."""
    return jsonify(_get_user_followups())


@followups_bp.route('/api', methods=['POST'])
@csrf.exempt
@login_required
def api_create():
    """Create a new follow-up."""
    data = request.get_json(silent=True) or {}
    required = ('student_name', 'type', 'due_date')
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({'error': f'Missing fields: {", ".join(missing)}'}), 400

    valid_types = ('check-in', 'referral', 'attendance-grades')
    if data['type'] not in valid_types:
        return jsonify({'error': f'Invalid type. Must be one of: {", ".join(valid_types)}'}), 400

    now = datetime.now(timezone.utc).isoformat()
    followup = {
        'id': str(uuid.uuid4()),
        'counselor_id': current_user.id,
        'student_name': data['student_name'].strip(),
        'student_id': data.get('student_id', ''),
        'grade': data.get('grade', ''),
        'type': data['type'],
        'due_date': data['due_date'],
        'notes': data.get('notes', '').strip(),
        'status': 'open',
        'created_at': now,
        'updated_at': now,
    }
    _save_user_followup(followup)
    return jsonify(followup), 201


@followups_bp.route('/api/<followup_id>', methods=['PATCH'])
@csrf.exempt
@login_required
def api_update(followup_id):
    """Update a follow-up's fields."""
    user_fups = _get_user_followups()
    followup = next((f for f in user_fups if f['id'] == followup_id), None)
    if not followup:
        return jsonify({'error': 'Not found'}), 404

    data = request.get_json(silent=True) or {}
    allowed = ('status', 'notes', 'due_date', 'type', 'student_name', 'grade')
    for key in allowed:
        if key in data:
            followup[key] = data[key]
    followup['updated_at'] = datetime.now(timezone.utc).isoformat()
    _save_user_followup(followup)
    return jsonify(followup)


@followups_bp.route('/api/<followup_id>/snooze', methods=['POST'])
@csrf.exempt
@login_required
def api_snooze(followup_id):
    """Push a follow-up's due_date forward by N days (default 3)."""
    user_fups = _get_user_followups()
    followup = next((f for f in user_fups if f['id'] == followup_id), None)
    if not followup:
        return jsonify({'error': 'Not found'}), 404

    data = request.get_json(silent=True) or {}
    days = int(data.get('days', 3))
    current_due = date.fromisoformat(followup['due_date'])
    new_due = current_due + timedelta(days=days)
    followup['due_date'] = new_due.isoformat()
    followup['updated_at'] = datetime.now(timezone.utc).isoformat()
    _save_user_followup(followup)
    return jsonify(followup)


@followups_bp.route('/api/<followup_id>', methods=['DELETE'])
@csrf.exempt
@login_required
def api_delete(followup_id):
    """Delete a follow-up."""
    user_fups = _get_user_followups()
    if not any(f['id'] == followup_id for f in user_fups):
        return jsonify({'error': 'Not found'}), 404
    _delete_user_followup(followup_id)
    return jsonify({'ok': True})


# ── Student Search (for autocomplete) ────────────────────────────

@followups_bp.route('/api/students', methods=['GET'])
@login_required
def api_student_search():
    """Search students in the counselor's caseload for autocomplete."""
    from app.models.student import Student
    from app import db

    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])

    students = Student.query.filter(
        Student.assigned_counselor_id == current_user.id,
        db.or_(
            Student.first_name.ilike(f'%{q}%'),
            Student.last_name.ilike(f'%{q}%'),
            Student.student_id_number.ilike(f'%{q}%'),
        )
    ).order_by(Student.last_name, Student.first_name).limit(10).all()

    return jsonify([
        {
            'id': s.student_id_number,
            'name': f'{s.first_name} {s.last_name}',
            'grade': s.grade_level or '',
        }
        for s in students
    ])
