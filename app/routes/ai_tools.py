"""AI Tools Hub routes — config-driven AI tool catalog."""
import json
import requests
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from app import db
from app.models.ai_tool_history import AIToolHistory
from app.models.student import Student
from app.models.note import Note
from app.models.attendance import AttendanceRecord
from app.models.grade import GradeRecord
from app.utils.ai_tools_registry import AI_TOOLS, CATEGORIES, get_tool, get_tools_by_category, search_tools
from app.utils import ollama_client
from app.utils.audit import log_action
from collections import defaultdict
from datetime import date, timedelta

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
    students = Student.query.order_by(Student.last_name, Student.first_name).all()
    recent = AIToolHistory.query.filter_by(
        user_id=current_user.id, tool_id=tool_id
    ).order_by(AIToolHistory.created_at.desc()).limit(5).all()
    return render_template('ai_tools/tool.html',
                           tool=tool,
                           categories=CATEGORIES,
                           students=students,
                           recent_history=recent,
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

    try:
        prompt = tool['prompt_template'].format(**filled_inputs)
    except KeyError as e:
        return jsonify({'error': f'Missing input: {e}'}), 400

    try:
        response = ollama_client.generate(prompt, system=tool['system_prompt'])
    except requests.Timeout:
        return jsonify({'error': (
            'The local AI model took too long to respond. This often happens on the first generation '
            'while the model loads into memory. Please try again — subsequent generations should be faster. '
            'If it keeps timing out, try a smaller/faster model in Settings (e.g. llama3.2:3b).'
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
    if not student:
        return ''

    lines = [f'\n--- STUDENT CONTEXT ---']
    lines.append(f'Name: {student.display_name}')
    lines.append(f'Grade: {student.grade_level or "N/A"}')

    designations = []
    if student.iep_status:
        designations.append('IEP')
    if student.section_504:
        designations.append('504 Plan')
    if student.el_status and student.el_status != 'EO':
        designations.append(f'EL: {student.el_status}')
    if designations:
        lines.append(f'Designations: {", ".join(designations)}')

    tags = [t.name for t in student.tags]
    if tags:
        lines.append(f'Tags: {", ".join(tags)}')

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
        lines.append(f'Attendance (30 days): {absences} absences, {tardies} tardies')

    grades = GradeRecord.query.filter_by(student_id=student_id).order_by(
        GradeRecord.school_year.desc(), GradeRecord.quarter.desc()
    ).limit(8).all()
    if grades:
        grade_lines = [f'  {g.course_name}: {g.letter_grade or "N/A"}' for g in grades]
        failing = [g for g in grades if g.letter_grade in ('F', 'D', 'D-', 'D+')]
        lines.append(f'Recent Grades ({len(failing)} failing):')
        lines.extend(grade_lines)

    notes = Note.query.filter_by(
        student_id=student_id, author_id=current_user.id
    ).order_by(Note.session_date.desc()).limit(5).all()
    if notes:
        lines.append('Recent Notes:')
        for n in notes:
            lines.append(f'  {n.session_date} [{n.note_type}]: {(n.content or "")[:120]}')

    lines.append('--- END STUDENT CONTEXT ---\n')
    return '\n'.join(lines)
