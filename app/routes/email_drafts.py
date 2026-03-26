"""Email Drafting — template-based email composer with merge fields."""
import json
import os
import uuid
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from app import csrf
from app.models.student import Student

email_drafts_bp = Blueprint('email_drafts', __name__)

DATA_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', '..', 'data')
TEMPLATES_FILE = os.path.join(DATA_DIR, 'email_templates.json')

# ── Built-in templates ────────────────────────────────────────────

DEFAULT_TEMPLATES = [
    {
        'id': 'attendance_concern',
        'name': 'Attendance Concern',
        'category': 'parent',
        'subject': 'Attendance Update for {{student_first_name}}',
        'body': (
            'Dear {{parent_name}},\n\n'
            'I hope this message finds you well. I am writing to share some '
            'attendance information regarding {{student_first_name}}.\n\n'
            'Over the past few weeks, {{student_first_name}} has accumulated '
            'several absences and/or tardies. Consistent attendance is one of '
            'the strongest predictors of academic success, and I want to make '
            'sure we can work together to support {{student_first_name}}.\n\n'
            'I would appreciate the opportunity to connect with you to discuss '
            'any challenges {{student_first_name}} may be facing. Please feel '
            'free to reach out to me at your convenience.\n\n'
            'Thank you for your partnership,\n'
            '{{counselor_name}}\n'
            'School Counselor'
        ),
        'builtin': True,
    },
    {
        'id': 'grade_update',
        'name': 'Grade Update',
        'category': 'parent',
        'subject': 'Academic Progress Update — {{student_first_name}} {{student_last_name}}',
        'body': (
            'Dear {{parent_name}},\n\n'
            'I wanted to reach out regarding {{student_first_name}}\'s academic '
            'progress. As we approach the end of the grading period, I want to '
            'ensure you are aware of how {{student_first_name}} is doing in '
            'their courses.\n\n'
            'Current grades and any areas of concern can be discussed in more '
            'detail at your convenience. I would be happy to set up a phone call '
            'or meeting to review {{student_first_name}}\'s progress together.\n\n'
            'Please don\'t hesitate to contact me.\n\n'
            'Best regards,\n'
            '{{counselor_name}}\n'
            'School Counselor'
        ),
        'builtin': True,
    },
    {
        'id': 'meeting_invite',
        'name': 'Meeting Invitation',
        'category': 'parent',
        'subject': 'Meeting Request — {{student_first_name}} {{student_last_name}}',
        'body': (
            'Dear {{parent_name}},\n\n'
            'I would like to schedule a meeting to discuss {{student_first_name}}\'s '
            'progress and support plan. Your involvement is important and I value '
            'your input as we work together to support {{student_first_name}}.\n\n'
            'Please let me know your availability for a meeting. I am available '
            'during the following times:\n\n'
            '- [Day/Time option 1]\n'
            '- [Day/Time option 2]\n'
            '- [Day/Time option 3]\n\n'
            'The meeting can be held in person or virtually, whichever is more '
            'convenient for you.\n\n'
            'Thank you,\n'
            '{{counselor_name}}\n'
            'School Counselor'
        ),
        'builtin': True,
    },
    {
        'id': 'teacher_referral',
        'name': 'Teacher Referral/Consult',
        'category': 'teacher',
        'subject': 'Student Referral — {{student_first_name}} {{student_last_name}}',
        'body': (
            'Hi {{teacher_name}},\n\n'
            'Thank you for your referral regarding {{student_first_name}} '
            '{{student_last_name}} (Grade {{grade_level}}). I wanted to let you '
            'know that I have received your concern and will be following up.\n\n'
            'I plan to check in with {{student_first_name}} this week. If you '
            'have any additional observations or information that would be '
            'helpful, please share them with me.\n\n'
            'I will keep you updated on next steps.\n\n'
            'Thank you,\n'
            '{{counselor_name}}'
        ),
        'builtin': True,
    },
    {
        'id': 'sst_follow_up',
        'name': 'SST Follow-Up',
        'category': 'admin',
        'subject': 'SST Follow-Up — {{student_first_name}} {{student_last_name}}',
        'body': (
            'Hello,\n\n'
            'I am writing to provide a follow-up on the Student Study Team '
            'meeting held for {{student_first_name}} {{student_last_name}} '
            '(Grade {{grade_level}}, ID: {{student_id}}).\n\n'
            'Summary of interventions discussed:\n'
            '- [Intervention 1]\n'
            '- [Intervention 2]\n'
            '- [Intervention 3]\n\n'
            'Next review date: [Date]\n\n'
            'Please reach out with any questions or updates.\n\n'
            '{{counselor_name}}\n'
            'School Counselor'
        ),
        'builtin': True,
    },
    {
        'id': 'college_reminder',
        'name': 'College App Reminder',
        'category': 'student',
        'subject': 'College Application Reminder',
        'body': (
            'Hi {{student_first_name}},\n\n'
            'This is a friendly reminder about upcoming college application '
            'deadlines. Please make sure you are keeping track of the following:\n\n'
            '- Application deadlines for your target schools\n'
            '- Personal statement / essay drafts\n'
            '- Letters of recommendation requests\n'
            '- FAFSA / financial aid applications\n'
            '- Transcript request submissions\n\n'
            'I am here to help with any part of the process. Feel free to stop '
            'by my office or schedule a time to meet.\n\n'
            'You\'ve got this!\n'
            '{{counselor_name}}'
        ),
        'builtin': True,
    },
    {
        'id': 'check_in',
        'name': 'Student Check-In',
        'category': 'student',
        'subject': 'Checking In',
        'body': (
            'Hi {{student_first_name}},\n\n'
            'I just wanted to check in and see how things are going for you. '
            'Whether it\'s academics, personal matters, or anything else — '
            'I\'m here to support you.\n\n'
            'Feel free to stop by my office anytime, or let me know a good '
            'time to chat.\n\n'
            'Take care,\n'
            '{{counselor_name}}'
        ),
        'builtin': True,
    },
]

MERGE_FIELDS = [
    ('{{student_first_name}}', 'Student first name'),
    ('{{student_last_name}}', 'Student last name'),
    ('{{student_full_name}}', 'Last, First'),
    ('{{student_id}}', 'Student ID number'),
    ('{{grade_level}}', 'Grade level'),
    ('{{parent_name}}', 'Parent/guardian name'),
    ('{{parent_email}}', 'Parent/guardian email'),
    ('{{counselor_name}}', 'Your display name'),
    ('{{teacher_name}}', 'Teacher name (manual)'),
    ('{{date}}', 'Today\'s date'),
]


# ── Helpers ────────────────────────────────────────────────────────

def _read_custom_templates():
    """Read user-created email templates."""
    if not os.path.exists(TEMPLATES_FILE):
        return []
    try:
        with open(TEMPLATES_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _write_custom_templates(templates):
    """Save user-created email templates."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(TEMPLATES_FILE, 'w') as f:
        json.dump(templates, f, indent=2, default=str)


def _all_templates():
    """Return built-in + user templates."""
    custom = _read_custom_templates()
    return DEFAULT_TEMPLATES + [t for t in custom
                                if t.get('counselor_id') == current_user.id]


def _merge(text, student, extra=None):
    """Replace merge fields in text with student data."""
    if not text:
        return text
    from datetime import date as d
    replacements = {
        '{{student_first_name}}': student.first_name or '',
        '{{student_last_name}}': student.last_name or '',
        '{{student_full_name}}': student.full_name or '',
        '{{student_id}}': student.student_id_number or '',
        '{{grade_level}}': str(student.grade_level or ''),
        '{{parent_name}}': student.parent_guardian_name or '[Parent/Guardian]',
        '{{parent_email}}': student.parent_guardian_email or '',
        '{{counselor_name}}': current_user.display_name or current_user.username,
        '{{date}}': d.today().strftime('%B %d, %Y'),
    }
    if extra:
        replacements.update(extra)
    for field, value in replacements.items():
        text = text.replace(field, value)
    return text


# ── Routes ─────────────────────────────────────────────────────────

@email_drafts_bp.route('/')
@login_required
def index():
    """Email drafting interface."""
    students = (Student.query
                .filter_by(assigned_counselor_id=current_user.id,
                           status='active')
                .order_by(Student.last_name, Student.first_name)
                .all())
    templates = _all_templates()
    categories = sorted(set(t.get('category', 'other') for t in templates))
    return render_template('email_drafts/index.html',
                           students=students,
                           templates=templates,
                           categories=categories,
                           merge_fields=MERGE_FIELDS)


@email_drafts_bp.route('/api/merge', methods=['POST'])
@csrf.exempt
@login_required
def api_merge():
    """Merge template fields with selected student's data."""
    data = request.get_json(silent=True) or {}
    student_id = data.get('student_id')
    subject = data.get('subject', '')
    body = data.get('body', '')

    if student_id:
        student = Student.query.filter_by(
            id=student_id,
            assigned_counselor_id=current_user.id).first()
        if student:
            extra = data.get('extra_fields', {})
            subject = _merge(subject, student, extra)
            body = _merge(body, student, extra)

    return jsonify({'subject': subject, 'body': body})


@email_drafts_bp.route('/api/ai-draft', methods=['POST'])
@csrf.exempt
@login_required
def api_ai_draft():
    """Use local AI to draft or improve an email."""
    from app.utils import ollama_client

    data = request.get_json(silent=True) or {}
    context = data.get('context', '')
    current_body = data.get('current_body', '')
    action = data.get('action', 'draft')  # 'draft' or 'improve'

    if not ollama_client.is_available():
        return jsonify({'error': 'AI is not available. Make sure Ollama is running.'}), 503

    if action == 'improve' and current_body:
        prompt = (
            f"Improve this email from a school counselor. Keep it professional, "
            f"warm, and concise. Maintain the same intent and merge fields "
            f"(like {{{{student_first_name}}}}).\n\n"
            f"Context: {context}\n\n"
            f"Original email:\n{current_body}"
        )
    else:
        prompt = (
            f"Write a brief, professional email from a school counselor. "
            f"Context: {context}\n"
            f"Use merge fields where appropriate: "
            f"{{{{student_first_name}}}}, {{{{parent_name}}}}, {{{{counselor_name}}}}, "
            f"{{{{grade_level}}}}, {{{{date}}}}.\n"
            f"Keep it warm but concise (under 150 words)."
        )

    system = (
        "You are a school counselor writing professional emails to parents, "
        "teachers, students, or administrators. Write clearly, warmly, and "
        "concisely. Use merge fields in double curly braces where appropriate."
    )

    try:
        result = ollama_client.generate(prompt, system=system, temperature=0.7)
        return jsonify({'ok': True, 'body': result})
    except Exception:
        return jsonify({'error': 'AI processing failed. Please try again.'}), 500


@email_drafts_bp.route('/api/templates', methods=['POST'])
@csrf.exempt
@login_required
def api_save_template():
    """Save a custom email template."""
    data = request.get_json(silent=True) or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Template name is required'}), 400

    templates = _read_custom_templates()
    template = {
        'id': str(uuid.uuid4()),
        'counselor_id': current_user.id,
        'name': name,
        'category': data.get('category', 'custom'),
        'subject': data.get('subject', ''),
        'body': data.get('body', ''),
        'builtin': False,
        'created_at': datetime.now(timezone.utc).isoformat(),
    }
    templates.append(template)
    _write_custom_templates(templates)
    return jsonify(template), 201


@email_drafts_bp.route('/api/templates/<template_id>', methods=['DELETE'])
@csrf.exempt
@login_required
def api_delete_template(template_id):
    """Delete a custom template."""
    templates = _read_custom_templates()
    templates = [t for t in templates
                 if not (t['id'] == template_id
                         and t.get('counselor_id') == current_user.id)]
    _write_custom_templates(templates)
    return jsonify({'ok': True})
