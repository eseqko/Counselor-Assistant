"""AI Tools Hub routes — config-driven AI tool catalog with workflow actions."""
import json
import requests
from datetime import date, datetime, timedelta
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from app import db
from app.models.ai_tool_history import AIToolHistory
from app.models.student import Student
from app.models.note import Note
from app.models.attendance import AttendanceRecord
from app.models.grade import GradeRecord
from app.models.calendar_event import CalendarEvent
from app.utils.ai_tools_registry import AI_TOOLS, CATEGORIES, get_tool, get_tools_by_category, search_tools
from app.utils import ollama_client
from app.utils.stream_helpers import stream_sse
from app.utils.context_budget import budget_prompt
from app.utils.audit import log_action
from app.models.knowledge_base import KnowledgeDocument, KnowledgeChunk
from app.utils.knowledge_base import build_knowledge_context

ai_tools_bp = Blueprint('ai_tools', __name__, template_folder='../templates/ai_tools')


@ai_tools_bp.route('/')
@login_required
def index():
    q = request.args.get('q', '').strip()
    category = request.args.get('category', '')
    if q:
        tools = search_tools(q)
    elif category:
        tools = [t for t in AI_TOOLS if t['category'] == category]
    else:
        tools = None
    tools_by_category = get_tools_by_category()
    return render_template('ai_tools/index.html',
                           tools_by_category=tools_by_category,
                           categories=CATEGORIES,
                           filtered_tools=tools,
                           search_query=q,
                           active_category=category,
                           ai_available=ollama_client.is_available())


@ai_tools_bp.route('/tool/<tool_id>')
@login_required
def tool_page(tool_id):
    tool = get_tool(tool_id)
    if not tool:
        flash('Tool not found.', 'error')
        return redirect(url_for('ai_tools.index'))
    # Scope to the counselor's own caseload — never list other counselors'
    # students or shadow students (school-wide comparison rows) by name.
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active'
    ).order_by(Student.last_name, Student.first_name).all()
    recent = AIToolHistory.query.filter_by(
        user_id=current_user.id, tool_id=tool_id
    ).order_by(AIToolHistory.created_at.desc()).limit(5).all()
    kb_doc_count = KnowledgeDocument.query.filter_by(user_id=current_user.id).count()
    return render_template('ai_tools/tool.html',
                           tool=tool,
                           categories=CATEGORIES,
                           students=students,
                           recent_history=recent,
                           kb_doc_count=kb_doc_count,
                           ai_available=ollama_client.is_available())


@ai_tools_bp.route('/generate', methods=['POST'])
@login_required
def generate():
    data = request.get_json()
    tool_id = data.get('tool_id')
    tool = get_tool(tool_id)
    if not tool:
        return jsonify({'error': 'Tool not found'}), 404

    student_id = data.get('student_id')
    inputs = data.get('inputs', {})

    student_context = ''
    if student_id and tool.get('supports_student_context'):
        student_context = _build_student_context(int(student_id))

    filled_inputs = {}
    for field in tool['inputs']:
        filled_inputs[field['name']] = inputs.get(field['name'], '')

    filled_inputs['student_context'] = student_context

    kb_context = ''
    all_chunks = KnowledgeChunk.query.join(KnowledgeDocument).filter(
        KnowledgeDocument.user_id == current_user.id
    ).all()
    if all_chunks:
        search_terms = ' '.join(v for v in filled_inputs.values() if v and v != student_context)
        search_terms += ' ' + tool['title']
        kb_context = build_knowledge_context(search_terms, all_chunks)

    filled_inputs['knowledge_context'] = kb_context

    try:
        prompt = tool['prompt_template'].format(**filled_inputs)
    except KeyError as e:
        return jsonify({'error': f'Missing input: {e}'}), 400

    system_prompt = tool['system_prompt']
    if kb_context:
        system_prompt += (
            '\n\nUse the district knowledge base below when relevant. '
            'Cite the source document.'
            + kb_context
        )

    try:
        prompt, system_prompt = budget_prompt(prompt, system_prompt)
        response = ollama_client.generate(prompt, system=system_prompt)
    except requests.Timeout:
        return jsonify({'error': (
            'The local AI model took too long to respond. This often happens on the first generation '
            'while the model loads into memory. Please try again — subsequent generations should be faster. '
            'If it keeps timing out, try a smaller model in Settings (e.g. gemma4:e2b).'
        )}), 504
    except requests.ConnectionError:
        return jsonify({'error': (
            'Could not reach Ollama. Make sure the Ollama server is running on your machine.'
        )}), 503
    except Exception as e:
        return jsonify({'error': f'AI generation failed: {str(e)}'}), 500

    entry = AIToolHistory(
        user_id=current_user.id,
        tool_id=tool_id,
        tool_title=tool['title'],
        student_id=int(student_id) if student_id else None,
        inputs_json=json.dumps(filled_inputs),
        output_text=response,
    )
    db.session.add(entry)
    db.session.commit()

    log_action('ai_tool_generate', 'ai_tool', entry.id,
               f'Generated: {tool["title"]}')

    return jsonify({'output': response, 'history_id': entry.id})


@ai_tools_bp.route('/generate-stream', methods=['POST'])
@login_required
def generate_stream():
    data = request.get_json()
    tool_id = data.get('tool_id')
    tool = get_tool(tool_id)
    if not tool:
        return jsonify({'error': 'Tool not found'}), 404

    student_id = data.get('student_id')
    inputs = data.get('inputs', {})

    student_context = ''
    if student_id and tool.get('supports_student_context'):
        student_context = _build_student_context(int(student_id))

    filled_inputs = {}
    for field in tool['inputs']:
        filled_inputs[field['name']] = inputs.get(field['name'], '')
    filled_inputs['student_context'] = student_context

    kb_context = ''
    all_chunks = KnowledgeChunk.query.join(KnowledgeDocument).filter(
        KnowledgeDocument.user_id == current_user.id
    ).all()
    if all_chunks:
        search_terms = ' '.join(v for v in filled_inputs.values() if v and v != student_context)
        search_terms += ' ' + tool['title']
        kb_context = build_knowledge_context(search_terms, all_chunks)
    filled_inputs['knowledge_context'] = kb_context

    try:
        prompt = tool['prompt_template'].format(**filled_inputs)
    except KeyError as e:
        return jsonify({'error': f'Missing input: {e}'}), 400

    system_prompt = tool['system_prompt']
    if kb_context:
        system_prompt += (
            '\n\nUse the district knowledge base below when relevant. '
            'Cite the source document.'
            + kb_context
        )

    return stream_sse(prompt, system=system_prompt)


@ai_tools_bp.route('/save-history', methods=['POST'])
@login_required
def save_history():
    data = request.get_json()
    tool_id = data.get('tool_id')
    tool = get_tool(tool_id)
    if not tool:
        return jsonify({'error': 'Tool not found'}), 404

    output_text = data.get('output', '').strip()
    if not output_text:
        return jsonify({'error': 'No output to save'}), 400

    student_id = data.get('student_id')
    inputs = data.get('inputs', {})

    entry = AIToolHistory(
        user_id=current_user.id,
        tool_id=tool_id,
        tool_title=tool['title'],
        student_id=int(student_id) if student_id else None,
        inputs_json=json.dumps(inputs),
        output_text=output_text,
    )
    db.session.add(entry)
    db.session.commit()

    log_action('ai_tool_generate', 'ai_tool', entry.id, f'Generated: {tool["title"]}')
    return jsonify({'ok': True, 'history_id': entry.id})


@ai_tools_bp.route('/history')
@login_required
def history():
    page = request.args.get('page', 1, type=int)
    q = request.args.get('q', '').strip()
    query = AIToolHistory.query.filter_by(user_id=current_user.id)
    if q:
        query = query.filter(
            AIToolHistory.tool_title.ilike(f'%{q}%') |
            AIToolHistory.output_text.ilike(f'%{q}%')
        )
    entries = query.order_by(AIToolHistory.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False)
    return render_template('ai_tools/history.html', entries=entries, search_query=q)


@ai_tools_bp.route('/history/<int:entry_id>')
@login_required
def history_detail(entry_id):
    entry = AIToolHistory.query.get_or_404(entry_id)
    if entry.user_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('ai_tools.history'))
    tool = get_tool(entry.tool_id)
    return jsonify({
        'tool_title': entry.tool_title,
        'inputs': json.loads(entry.inputs_json),
        'output': entry.output_text,
        'student_id': entry.student_id,
        'created_at': entry.created_at.isoformat(),
        'tool': {'id': tool['id'], 'title': tool['title']} if tool else None,
    })


def _build_student_context(student_id):
    student = Student.query.get(student_id)
    # Ownership guard: never build PII context (name, grade, IEP/504, grades,
    # attendance) for a student who isn't on this counselor's caseload. Blocks
    # IDOR via a posted student_id and keeps shadow students out of AI prompts.
    if not student or (
        current_user.role != 'admin'
        and student.assigned_counselor_id != current_user.id
    ):
        return ''

    lines = [f'\n--- STUDENT CONTEXT ---']
    lines.append(f'Name: {student.display_name}, Grade: {student.grade_level or "N/A"}')

    designations = []
    if student.iep_status:
        designations.append('IEP')
    if student.section_504:
        designations.append('504')
    if student.el_status and student.el_status != 'EO':
        designations.append(f'EL:{student.el_status}')
    if designations:
        lines.append(f'Designations: {", ".join(designations)}')

    thirty_days = date.today() - timedelta(days=30)
    absences = AttendanceRecord.query.filter(
        AttendanceRecord.student_id == student_id,
        AttendanceRecord.date >= thirty_days,
        AttendanceRecord.status == 'absent'
    ).count()
    tardies = AttendanceRecord.query.filter(
        AttendanceRecord.student_id == student_id,
        AttendanceRecord.date >= thirty_days,
        AttendanceRecord.status == 'tardy'
    ).count()
    if absences or tardies:
        lines.append(f'Attendance (30d): {absences} absent, {tardies} tardy')

    grades = GradeRecord.query.filter_by(student_id=student_id).order_by(
        GradeRecord.school_year.desc(), GradeRecord.quarter.desc()
    ).limit(5).all()
    if grades:
        failing = [g for g in grades if g.letter_grade in ('F', 'D', 'D-', 'D+')]
        grade_strs = [f'{g.course_name}:{g.letter_grade or "N/A"}' for g in grades]
        lines.append(f'Grades ({len(failing)} failing): {", ".join(grade_strs)}')

    notes = Note.query.filter_by(
        student_id=student_id, author_id=current_user.id
    ).order_by(Note.session_date.desc()).limit(3).all()
    if notes:
        lines.append('Recent Notes:')
        for n in notes:
            lines.append(f'  {n.session_date} [{n.note_type}]: {(n.content or "")[:80]}')

    lines.append('--- END STUDENT CONTEXT ---\n')
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Workflow action endpoints — wire AI output into counseling workflow
# ---------------------------------------------------------------------------

@ai_tools_bp.route('/actions/save-note', methods=['POST'])
@login_required
def action_save_note():
    data = request.get_json()
    content = data.get('content', '').strip()
    if not content:
        return jsonify({'ok': False, 'error': 'No content provided'}), 400

    student_id = data.get('student_id')
    if not student_id:
        return jsonify({'ok': False, 'error': 'A student must be linked to save a note'}), 400

    note = Note(
        student_id=int(student_id),
        author_id=current_user.id,
        note_type=data.get('note_type', 'observation'),
        title=data.get('title', 'AI-Generated Note'),
        content=content,
        session_date=date.today(),
        delivery_method='in_person',
    )
    db.session.add(note)
    db.session.commit()
    log_action('note_create', 'note', note.id, f'Created from AI Tools: {note.title}')
    return jsonify({'ok': True, 'note_id': note.id, 'message': 'Note saved successfully.'})


@ai_tools_bp.route('/actions/log-service', methods=['POST'])
@login_required
def action_log_service():
    data = request.get_json()
    description = data.get('content', '').strip()
    if not description:
        return jsonify({'ok': False, 'error': 'No content provided'}), 400

    student_id = data.get('student_id')
    if not student_id:
        return jsonify({'ok': False, 'error': 'A student must be linked to log a service'}), 400

    note = Note(
        student_id=int(student_id),
        author_id=current_user.id,
        session_date=date.today(),
        note_type=data.get('service_type', 'student_conference'),
        title=data.get('title', 'AI-Assisted Session'),
        content=description,
        duration_minutes=data.get('duration', 30),
        asca_domain=data.get('asca_domain', ''),
    )
    db.session.add(note)
    db.session.commit()
    log_action('create', 'note', note.id, f'Created from AI Tools: {note.title}')
    return jsonify({'ok': True, 'record_id': note.id, 'message': 'Note logged.'})


@ai_tools_bp.route('/actions/add-calendar', methods=['POST'])
@login_required
def action_add_calendar():
    data = request.get_json()
    title = data.get('title', '').strip()
    if not title:
        return jsonify({'ok': False, 'error': 'Title is required'}), 400

    event_date = data.get('date')
    if event_date:
        start = datetime.strptime(event_date, '%Y-%m-%d').replace(hour=9, minute=0)
    else:
        tomorrow = date.today() + timedelta(days=1)
        start = datetime.combine(tomorrow, datetime.min.time()).replace(hour=9, minute=0)

    event = CalendarEvent(
        owner_id=current_user.id,
        title=title,
        description=data.get('content', ''),
        start_datetime=start,
        end_datetime=start + timedelta(hours=1),
        event_type=data.get('event_type', 'follow_up'),
        student_id=int(data['student_id']) if data.get('student_id') else None,
    )
    db.session.add(event)
    db.session.commit()
    log_action('calendar_create', 'calendar_event', event.id, f'Created from AI Tools: {event.title}')
    return jsonify({'ok': True, 'event_id': event.id, 'message': f'Calendar event created for {start.strftime("%b %d")}.'})


@ai_tools_bp.route('/actions/create-followup', methods=['POST'])
@login_required
def action_create_followup():
    data = request.get_json()
    notes_text = data.get('content', '').strip()
    student_id = data.get('student_id')
    student_name = ''
    if student_id:
        s = Student.query.get(int(student_id))
        # Only resolve names for caseload students (never shadows/other caseloads).
        if s and (current_user.role == 'admin'
                  or s.assigned_counselor_id == current_user.id):
            student_name = s.display_name

    due_date = data.get('due_date')
    if not due_date:
        due_date = (date.today() + timedelta(days=7)).isoformat()

    import os
    followups_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        'data', 'followups.json'
    )
    followups = []
    if os.path.exists(followups_path):
        with open(followups_path, 'r') as f:
            followups = json.load(f)

    import uuid
    entry = {
        'id': str(uuid.uuid4()),
        'student_name': student_name or data.get('title', 'Follow-up'),
        'student_id': str(student_id) if student_id else '',
        'grade': '',
        'type': data.get('followup_type', 'check-in'),
        'due_date': due_date,
        'notes': notes_text[:500],
        'completed': False,
        'created_at': datetime.utcnow().isoformat(),
    }
    followups.append(entry)
    with open(followups_path, 'w') as f:
        json.dump(followups, f, indent=2)

    return jsonify({'ok': True, 'followup_id': entry['id'], 'message': f'Follow-up created for {due_date}.'})


@ai_tools_bp.route('/actions/save-email-draft', methods=['POST'])
@login_required
def action_save_email_draft():
    data = request.get_json()
    body = data.get('content', '').strip()
    if not body:
        return jsonify({'ok': False, 'error': 'No content provided'}), 400

    import os
    templates_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        'data', 'email_custom_templates.json'
    )
    templates = []
    if os.path.exists(templates_path):
        with open(templates_path, 'r') as f:
            templates = json.load(f)

    import uuid
    template = {
        'id': str(uuid.uuid4()),
        'name': data.get('title', 'AI-Generated Draft'),
        'section': 'email',
        'category': 'ai_generated',
        'subject': data.get('subject', ''),
        'body': body,
    }
    templates.append(template)
    with open(templates_path, 'w') as f:
        json.dump(templates, f, indent=2)

    return jsonify({'ok': True, 'template_id': template['id'], 'message': 'Email draft saved to templates.'})


@ai_tools_bp.route('/actions/translate', methods=['POST'])
@login_required
def action_translate():
    data = request.get_json()
    text = data.get('content', '').strip()
    if not text:
        return jsonify({'ok': False, 'error': 'No text to translate'}), 400

    language = data.get('language', 'Spanish')
    system = (
        f'You are a professional translator. Translate the following text to {language}. '
        f'Preserve the formatting, tone, and meaning. Output only the translation.'
    )
    try:
        translated = ollama_client.generate(text, system=system, temperature=0.3)
    except requests.Timeout:
        return jsonify({'ok': False, 'error': 'Translation timed out. Try again.'}), 504
    except Exception as e:
        return jsonify({'ok': False, 'error': f'Translation failed: {str(e)}'}), 500

    return jsonify({'ok': True, 'translated': translated, 'language': language})


@ai_tools_bp.route('/actions/translate-stream', methods=['POST'])
@login_required
def action_translate_stream():
    data = request.get_json()
    text = data.get('content', '').strip()
    if not text:
        return jsonify({'ok': False, 'error': 'No text to translate'}), 400

    language = data.get('language', 'Spanish')
    system = (
        f'You are a professional translator. Translate the following text to {language}. '
        f'Preserve the formatting, tone, and meaning. Output only the translation.'
    )
    return stream_sse(text, system=system, temperature=0.3)
