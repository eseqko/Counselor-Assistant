"""Mail Merge — generate personalized letters for students (e.g. graduation risk)."""
import json
import os
from datetime import date
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from app.models.student import Student
from app.models.grade import GradeRecord
from app.routes.graduation import _build_student_grad_data, TOTAL_REQUIRED
from app.utils.helpers import current_school_year

mail_merge_bp = Blueprint('mail_merge', __name__)

DATA_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', '..', 'data')
TEMPLATES_FILE = os.path.join(DATA_DIR, 'letter_templates.json')


# ── Built-in letter templates ───────────────────────────────────

BUILTIN_TEMPLATES = [
    {
        'id': 'grad_risk_senior',
        'name': 'Senior At-Risk of Not Graduating',
        'category': 'graduation',
        'body': (
            '{{date}}\n\n'
            'To: Parent/Guardian of {{student_name}}\n'
            'Address: {{address}}\n\n'
            'Re: URGENT \u2014 {{student_first_name}}\u2019s Graduation Status (Class of {{grad_year}})\n\n'
            'Dear Parent of {{student_first_name}},\n\n'
            '{{student_first_name}} is at risk of not graduating in May {{grad_year}} due to a credit deficiency. '
            'Immediate action is required. {{student_first_name}} must pass the following classes they are '
            'currently enrolled in and additional courses:\n\n'
            '{{current_courses}}\n\n'
            'Graduation Requirements:\n'
            '  \u2022 225 total credits.\n'
            '  \u2022 Pass Specific Subject Requirements (see enclosed transcript).\n\n'
            'Time-Sensitive Solutions (this school year, {{school_year}}):\n'
            'Actions to be taken now:\n'
            '  \u2022 Register for APEX after school courses: In-person after school. Please see your counselor to register if you haven\u2019t done so.\n'
            '  \u2022 Flex Time: Sign up to see your teachers in classes you need in order to graduate (Tuesdays and Thursdays 11:35am-12:10pm)\n'
            '  \u2022 24/7 Tutoring: Access Paper.co with your School Google Account in order to receive online tutoring 24 hours a day/ 7 days a week.\n'
            '  \u2022 Thornton High School: Transfers to Thornton High School are done Quarterly. Please contact your student\u2019s counselor for this option.\n\n'
            'If you do not graduate in May:\n'
            'JUHSD Senior Studies (June {{grad_year}}):\n'
            '  \u2022 Earn up to 25 credits through APEX.\n\n'
            'Critical Next Steps:\n'
            '  1. Schedule a Meeting:\n'
            '     Please call 650 550 7787 to schedule an appointment with your student\u2019s counselor\n'
            '  2. Monitor Progress:\n'
            '     \u2022 Check ParentVUE for real-time updates.\n\n'
            'Consequences of Inaction:\n'
            'Without these credits, {{student_first_name}} will not receive a diploma in May {{grad_year}}, and '
            'cannot participate in Graduation activities at Jefferson High School. Let\u2019s collaborate to '
            'ensure their success.\n\n\n'
            '{{counselor_name}}, School Counselor\n'
            '(650) 550-7798 | jvillalobos@jeffersonunion.net | 6996 Mission St. Daly City, CA 94014'
        ),
        'builtin': True,
    },
]


def _load_custom_templates():
    """Load user-saved letter templates from disk."""
    if not os.path.exists(TEMPLATES_FILE):
        return []
    try:
        with open(TEMPLATES_FILE) as f:
            return [t for t in json.load(f) if t.get('counselor_id') == current_user.id]
    except (json.JSONDecodeError, IOError):
        return []


def _save_custom_templates(templates):
    """Save templates list to disk."""
    os.makedirs(DATA_DIR, exist_ok=True)
    # Load ALL templates (including other counselors'), update ours
    all_templates = []
    if os.path.exists(TEMPLATES_FILE):
        try:
            with open(TEMPLATES_FILE) as f:
                all_templates = [t for t in json.load(f) if t.get('counselor_id') != current_user.id]
        except (json.JSONDecodeError, IOError):
            pass
    all_templates.extend(templates)
    with open(TEMPLATES_FILE, 'w') as f:
        json.dump(all_templates, f, indent=2)


def _grad_year():
    """Calendar year the current school year graduates in (e.g. '2027')."""
    return current_school_year().split('-')[1]


def _get_current_courses(student_id):
    """Get the student's current-year courses as a formatted string."""
    current_year = current_school_year()
    grades = GradeRecord.query.filter_by(
        student_id=student_id,
        school_year=current_year,
    ).order_by(GradeRecord.period).all()

    if not grades:
        return '(No current course data available)'

    # Deduplicate by course name, show latest quarter
    seen = {}
    for g in grades:
        key = g.course_name
        if key not in seen or (g.quarter or 0) > (seen[key].quarter or 0):
            seen[key] = g
    lines = []
    for g in seen.values():
        grade_str = g.letter_grade or ''
        # `is_passing` is None for 'NM' (teacher hasn't graded yet) — a bare
        # falsy test printed "NOT PASSING" to a parent for an ungraded course.
        if g.is_passing:
            status = 'Passing'
        elif g.is_passing is False:
            status = 'NOT PASSING'
        else:
            status = 'Not Yet Graded'
        lines.append(f'  \u2022 {g.course_name} \u2014 Current Grade: {grade_str} ({status})')
    return '\n'.join(lines) if lines else '(No current course data available)'


def _merge_letter(template_body, student, extra=None):
    """Replace merge fields in template text."""
    grad_data = _build_student_grad_data(student)
    fields = {
        '{{student_name}}': f'{student.first_name} {student.last_name}',
        '{{student_first_name}}': student.first_name or '',
        '{{student_last_name}}': student.last_name or '',
        '{{student_id}}': student.student_id_number or '',
        '{{grade_level}}': str(student.grade_level or ''),
        '{{address}}': student.address or '[No address on file]',
        '{{parent_name}}': student.parent_guardian_name or 'Parent/Guardian',
        '{{parent_email}}': student.parent_guardian_email or '',
        '{{parent_phone}}': student.parent_guardian_phone or '',
        '{{counselor_name}}': current_user.display_name or current_user.username,
        '{{date}}': date.today().strftime('%B %d, %Y'),
        # Derived from the calendar, not hardcoded — these appear in letters
        # that go to parents, where a stale year is worse than no year.
        '{{grad_year}}': _grad_year(),
        '{{school_year}}': current_school_year(),
        '{{credits_completed}}': str(grad_data['total_completed']),
        '{{credits_needed}}': str(grad_data['total_needed']),
        '{{credits_required}}': str(TOTAL_REQUIRED),
        '{{progress_pct}}': str(grad_data['pct']),
        '{{risk_level}}': grad_data['risk'],
        '{{current_courses}}': _get_current_courses(student.id),
    }
    if extra:
        fields.update(extra)
    text = template_body
    for key, val in fields.items():
        text = text.replace(key, val)
    return text


@mail_merge_bp.route('/')
@login_required
def index():
    """Mail merge UI — select template, pick students, preview & print."""
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id,
        status='active'
    ).order_by(Student.grade_level.desc(), Student.last_name).all()

    # Build grad data for filtering
    student_data = []
    for s in students:
        gd = _build_student_grad_data(s)
        student_data.append({
            'id': s.id,
            'name': f'{s.last_name}, {s.first_name}',
            'display_name': f'{s.first_name} {s.last_name}',
            'grade_level': s.grade_level,
            'risk': gd['risk'],
            'credits_completed': gd['total_completed'],
            'credits_needed': gd['total_needed'],
            'pct': gd['pct'],
        })

    templates = BUILTIN_TEMPLATES + _load_custom_templates()
    return render_template('mail_merge/index.html',
                           students=student_data,
                           templates=templates)


@mail_merge_bp.route('/api/preview', methods=['POST'])
@login_required
def preview():
    """Generate merged letter previews for selected students."""
    data = request.get_json()
    template_id = data.get('template_id', '')
    student_ids = data.get('student_ids', [])
    custom_body = data.get('custom_body', '')

    # Find template
    all_templates = BUILTIN_TEMPLATES + _load_custom_templates()
    template_body = custom_body
    if not template_body:
        for t in all_templates:
            if t['id'] == template_id:
                template_body = t['body']
                break

    if not template_body:
        return jsonify({'ok': False, 'error': 'No template selected'}), 400

    letters = []
    for sid in student_ids:
        student = Student.query.get(sid)
        if not student or student.assigned_counselor_id != current_user.id:
            continue
        merged = _merge_letter(template_body, student)
        letters.append({
            'student_id': sid,
            'student_name': f'{student.first_name} {student.last_name}',
            'content': merged,
        })

    return jsonify({'ok': True, 'letters': letters})


@mail_merge_bp.route('/api/template', methods=['POST'])
@login_required
def save_template():
    """Save a custom letter template."""
    data = request.get_json()
    name = data.get('name', '').strip()
    body = data.get('body', '').strip()
    if not name or not body:
        return jsonify({'ok': False, 'error': 'Name and body are required'}), 400

    templates = _load_custom_templates()
    import uuid
    new_template = {
        'id': str(uuid.uuid4())[:8],
        'name': name,
        'category': data.get('category', 'custom'),
        'body': body,
        'counselor_id': current_user.id,
        'builtin': False,
    }
    templates.append(new_template)
    _save_custom_templates(templates)
    return jsonify({'ok': True, 'template': new_template})


@mail_merge_bp.route('/api/template/<template_id>', methods=['DELETE'])
@login_required
def delete_template(template_id):
    """Delete a custom letter template."""
    templates = _load_custom_templates()
    templates = [t for t in templates if t['id'] != template_id]
    _save_custom_templates(templates)
    return jsonify({'ok': True})
