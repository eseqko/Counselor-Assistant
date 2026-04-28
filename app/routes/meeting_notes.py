"""Meeting Notes routes -- live note-taking with @student mentions."""
import re
import os
import uuid
import tempfile
from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from markupsafe import escape
from app import db, csrf
from app.models.meeting_note import MeetingNote, meeting_note_students
from app.models.student import Student
from app.utils.audit import log_action
from app.utils import ollama_client

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
            note_format=request.form.get('note_format', 'flow'),
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
        note.note_format = request.form.get('note_format', note.note_format or 'flow')
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


# ---------- Audio Recording + AI Summarization ----------

def _whisper_available():
    """Check if faster-whisper is installed."""
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


@meeting_notes_bp.route('/api/audio-status')
@login_required
def audio_status():
    """Check whether audio transcription is available."""
    return jsonify({
        'whisper_available': _whisper_available(),
        'ollama_available': ollama_client.is_available(),
    })


@meeting_notes_bp.route('/api/transcribe', methods=['POST'])
@csrf.exempt
@login_required
def transcribe_audio():
    """Receive audio blob, transcribe with Whisper, summarize with Ollama.

    Flow: browser MediaRecorder -> upload -> Whisper STT -> Ollama summary
    -> return both transcript + summary for user approval -> audio deleted.
    """
    if 'audio' not in request.files:
        return jsonify({'error': 'No audio file uploaded'}), 400

    audio_file = request.files['audio']
    meeting_type = request.form.get('meeting_type', 'general')

    # Save to temp file
    upload_dir = current_app.config.get('UPLOAD_FOLDER', 'data/uploads')
    os.makedirs(upload_dir, exist_ok=True)
    ext = 'wav' if audio_file.filename.endswith('.wav') else 'webm'
    tmp_name = f'audio_{uuid.uuid4().hex}.{ext}'
    tmp_path = os.path.join(upload_dir, tmp_name)

    try:
        audio_file.save(tmp_path)

        # --- Transcribe ---
        if not _whisper_available():
            return jsonify({'error': 'Speech-to-text not available. Install faster-whisper: pip install faster-whisper'}), 503

        try:
            from faster_whisper import WhisperModel
            # Use 'tiny' for speed/memory; 'base' for accuracy. int8 keeps RAM low.
            file_size_mb = os.path.getsize(tmp_path) / (1024 * 1024)
            model_size = 'base' if file_size_mb < 20 else 'tiny'
            model = WhisperModel(model_size, device='cpu', compute_type='int8')
            segments, info = model.transcribe(tmp_path, beam_size=5)
            transcript = ' '.join(seg.text.strip() for seg in segments)
            del model  # free model memory immediately
        except Exception as e:
            current_app.logger.error(f'Whisper transcription error: {e}')
            return jsonify({'error': f'Transcription failed: {str(e)}. Make sure ffmpeg is installed (apt install ffmpeg).'}), 500

        if not transcript.strip():
            return jsonify({'error': 'Could not detect any speech in the recording.'}), 422

        # --- Summarize with Ollama ---
        summary = transcript  # fallback if Ollama unavailable
        if ollama_client.is_available():
            meeting_label = meeting_type.replace('_', ' ').title()
            prompt = f"""Summarize the following transcript from a {meeting_label} meeting into clean, organized meeting notes.

TRANSCRIPT:
{transcript}

Format the summary as:
- A brief overview paragraph
- Key discussion points (bullet points)
- Decisions made (if any)
- Action items (if any, prefix with #action)
- Follow-ups needed (if any, prefix with #followup)

Keep it concise and professional. Use #action and #followup tags inline."""

            system = ("Summarize meeting transcripts into clean, organized notes. "
                      "Be concise. Preserve important details and names. Use the tag format requested.")
            try:
                summary = ollama_client.generate(prompt, system=system, temperature=0.3)
            except Exception:
                summary = transcript  # Fall back to raw transcript

        return jsonify({
            'transcript': transcript,
            'summary': summary,
            'duration_seconds': round(info.duration, 1) if hasattr(info, 'duration') else None,
        })

    except Exception as e:
        current_app.logger.error(f'Audio processing error: {e}')
        return jsonify({'error': f'Audio processing failed: {str(e)}'}), 500
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


@meeting_notes_bp.route('/api/transcribe-stream', methods=['POST'])
@csrf.exempt
@login_required
def transcribe_audio_stream():
    """Transcribe audio, then stream AI summary via SSE.

    Returns transcript immediately in the first SSE event, then streams
    the Ollama summary token by token.
    """
    import json as _json
    from flask import Response, stream_with_context

    if 'audio' not in request.files:
        return jsonify({'error': 'No audio file uploaded'}), 400

    audio_file = request.files['audio']
    meeting_type = request.form.get('meeting_type', 'general')

    upload_dir = current_app.config.get('UPLOAD_FOLDER', 'data/uploads')
    os.makedirs(upload_dir, exist_ok=True)
    ext = 'wav' if audio_file.filename.endswith('.wav') else 'webm'
    tmp_name = f'audio_{uuid.uuid4().hex}.{ext}'
    tmp_path = os.path.join(upload_dir, tmp_name)

    try:
        audio_file.save(tmp_path)

        if not _whisper_available():
            return jsonify({'error': 'Speech-to-text not available. Install faster-whisper: pip install faster-whisper'}), 503

        try:
            from faster_whisper import WhisperModel
            file_size_mb = os.path.getsize(tmp_path) / (1024 * 1024)
            model_size = 'base' if file_size_mb < 20 else 'tiny'
            model = WhisperModel(model_size, device='cpu', compute_type='int8')
            segments, info = model.transcribe(tmp_path, beam_size=5)
            transcript = ' '.join(seg.text.strip() for seg in segments)
            duration = round(info.duration, 1) if hasattr(info, 'duration') else None
            del model
        except Exception as e:
            current_app.logger.error(f'Whisper transcription error: {e}')
            return jsonify({'error': f'Transcription failed: {str(e)}'}), 500

        if not transcript.strip():
            return jsonify({'error': 'Could not detect any speech in the recording.'}), 422

    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    def generate():
        yield f"data: {_json.dumps({'transcript': transcript, 'duration_seconds': duration})}\n\n"

        if not ollama_client.is_available():
            yield f"data: {_json.dumps({'done': True, 'full_text': transcript})}\n\n"
            return

        meeting_label = meeting_type.replace('_', ' ').title()
        prompt = f"""Summarize the following transcript from a {meeting_label} meeting into clean, organized meeting notes.

TRANSCRIPT:
{transcript}

Format the summary as:
- A brief overview paragraph
- Key discussion points (bullet points)
- Decisions made (if any)
- Action items (if any, prefix with #action)
- Follow-ups needed (if any, prefix with #followup)

Keep it concise and professional. Use #action and #followup tags inline."""

        system = ("You are a school counselor's assistant. Summarize meeting transcripts into "
                  "clean, organized notes. Be concise and professional. Preserve important details "
                  "and names mentioned. Use the tag format requested.")

        full_text = []
        try:
            for token, done in ollama_client.generate_stream(
                    prompt, system=system, temperature=0.3):
                full_text.append(token)
                if token:
                    yield f"data: {_json.dumps({'token': token})}\n\n"
                if done:
                    yield f"data: {_json.dumps({'done': True, 'full_text': ''.join(full_text).strip()})}\n\n"
        except Exception as e:
            yield f"data: {_json.dumps({'done': True, 'full_text': transcript})}\n\n"

    return Response(
        stream_with_context(generate()),
        content_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )
