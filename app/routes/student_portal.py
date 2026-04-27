"""Student portal — public AI tools accessible via shareable link."""
import json
from flask import Blueprint, render_template, request, jsonify
from app import db, csrf
from app.models.user import User
from app.utils.student_tools_registry import STUDENT_TOOLS, get_student_tool
from app.utils import ollama_client

student_portal_bp = Blueprint('student_portal', __name__,
                              template_folder='../templates/student_portal')


def _get_counselor_by_token(token):
    return User.query.filter_by(calendar_feed_token=token).first()


@student_portal_bp.route('/<token>')
def index(token):
    counselor = _get_counselor_by_token(token)
    if not counselor:
        return render_template('student_portal/invalid.html'), 404
    return render_template('student_portal/index.html',
                           tools=STUDENT_TOOLS,
                           counselor=counselor,
                           token=token,
                           ai_available=ollama_client.is_available())


@student_portal_bp.route('/<token>/tool/<tool_id>')
def tool_page(token, tool_id):
    counselor = _get_counselor_by_token(token)
    if not counselor:
        return render_template('student_portal/invalid.html'), 404
    tool = get_student_tool(tool_id)
    if not tool:
        return render_template('student_portal/invalid.html'), 404
    return render_template('student_portal/tool.html',
                           tool=tool,
                           counselor=counselor,
                           token=token,
                           ai_available=ollama_client.is_available())


@student_portal_bp.route('/<token>/generate', methods=['POST'])
@csrf.exempt
def generate(token):
    counselor = _get_counselor_by_token(token)
    if not counselor:
        return jsonify({'error': 'Invalid portal link'}), 404

    data = request.get_json()
    tool_id = data.get('tool_id')
    tool = get_student_tool(tool_id)
    if not tool:
        return jsonify({'error': 'Tool not found'}), 404

    inputs = data.get('inputs', {})
    filled = {}
    for field in tool['inputs']:
        filled[field['name']] = inputs.get(field['name'], '')

    try:
        prompt = tool['prompt_template'].format(**filled)
    except KeyError as e:
        return jsonify({'error': f'Missing input: {e}'}), 400

    if not ollama_client.is_available():
        return jsonify({'error': 'AI is temporarily unavailable. Please try again later.'}), 503

    try:
        response = ollama_client.generate(prompt, system=tool['system_prompt'])
    except Exception:
        return jsonify({'error': 'AI generation took too long. Please try again.'}), 504

    return jsonify({'output': response})
