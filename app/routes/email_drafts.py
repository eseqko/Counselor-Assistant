"""Communication Drafts — emails, Google Classroom posts, newsletters, quick messages."""
import json
import os
import uuid
from datetime import datetime, date as _date, timezone
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from app import csrf
from app.models.student import Student

email_drafts_bp = Blueprint('email_drafts', __name__)

DATA_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', '..', 'data')
TEMPLATES_FILE = os.path.join(DATA_DIR, 'comm_templates.json')

# ── Sections ──────────────────────────────────────────────────────

SECTIONS = [
    {'id': 'email', 'label': 'Emails', 'icon': '&#9993;',
     'has_subject': True, 'placeholder': 'Compose your email...'},
    {'id': 'classroom', 'label': 'Google Classroom', 'icon': '&#127891;',
     'has_subject': True, 'placeholder': 'Write your classroom post...'},
    {'id': 'newsletter', 'label': 'Newsletters', 'icon': '&#128240;',
     'has_subject': True, 'placeholder': 'Draft your newsletter content...'},
    {'id': 'quick', 'label': 'Quick Messages', 'icon': '&#128172;',
     'has_subject': False, 'placeholder': 'Type a quick message...'},
]

# ── Built-in templates ────────────────────────────────────────────

DEFAULT_TEMPLATES = [
    # ── Email templates ──
    {
        'id': 'attendance_concern', 'section': 'email',
        'name': 'Attendance Concern', 'category': 'parent',
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
            '{{counselor_name}}\nSchool Counselor'
        ),
        'builtin': True,
    },
    {
        'id': 'grade_update', 'section': 'email',
        'name': 'Grade Update', 'category': 'parent',
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
            'Best regards,\n{{counselor_name}}\nSchool Counselor'
        ),
        'builtin': True,
    },
    {
        'id': 'meeting_invite', 'section': 'email',
        'name': 'Meeting Invitation', 'category': 'parent',
        'subject': 'Meeting Request — {{student_first_name}} {{student_last_name}}',
        'body': (
            'Dear {{parent_name}},\n\n'
            'I would like to schedule a meeting to discuss {{student_first_name}}\'s '
            'progress and support plan. Your involvement is important and I value '
            'your input as we work together to support {{student_first_name}}.\n\n'
            'Please let me know your availability for a meeting. I am available '
            'during the following times:\n\n'
            '- [Day/Time option 1]\n- [Day/Time option 2]\n- [Day/Time option 3]\n\n'
            'The meeting can be held in person or virtually, whichever is more '
            'convenient for you.\n\nThank you,\n{{counselor_name}}\nSchool Counselor'
        ),
        'builtin': True,
    },
    {
        'id': 'teacher_referral', 'section': 'email',
        'name': 'Teacher Referral/Consult', 'category': 'teacher',
        'subject': 'Student Referral — {{student_first_name}} {{student_last_name}}',
        'body': (
            'Hi {{teacher_name}},\n\n'
            'Thank you for your referral regarding {{student_first_name}} '
            '{{student_last_name}} (Grade {{grade_level}}). I wanted to let you '
            'know that I have received your concern and will be following up.\n\n'
            'I plan to check in with {{student_first_name}} this week. If you '
            'have any additional observations or information that would be '
            'helpful, please share them with me.\n\n'
            'I will keep you updated on next steps.\n\nThank you,\n{{counselor_name}}'
        ),
        'builtin': True,
    },
    {
        'id': 'sst_follow_up', 'section': 'email',
        'name': 'SST Follow-Up', 'category': 'admin',
        'subject': 'SST Follow-Up — {{student_first_name}} {{student_last_name}}',
        'body': (
            'Hello,\n\n'
            'I am writing to provide a follow-up on the Student Study Team '
            'meeting held for {{student_first_name}} {{student_last_name}} '
            '(Grade {{grade_level}}, ID: {{student_id}}).\n\n'
            'Summary of interventions discussed:\n'
            '- [Intervention 1]\n- [Intervention 2]\n- [Intervention 3]\n\n'
            'Next review date: [Date]\n\n'
            'Please reach out with any questions or updates.\n\n'
            '{{counselor_name}}\nSchool Counselor'
        ),
        'builtin': True,
    },
    {
        'id': 'college_reminder', 'section': 'email',
        'name': 'College App Reminder', 'category': 'student',
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
            'You\'ve got this!\n{{counselor_name}}'
        ),
        'builtin': True,
    },
    {
        'id': 'check_in_email', 'section': 'email',
        'name': 'Student Check-In', 'category': 'student',
        'subject': 'Checking In',
        'body': (
            'Hi {{student_first_name}},\n\n'
            'I just wanted to check in and see how things are going for you. '
            'Whether it\'s academics, personal matters, or anything else — '
            'I\'m here to support you.\n\n'
            'Feel free to stop by my office anytime, or let me know a good '
            'time to chat.\n\nTake care,\n{{counselor_name}}'
        ),
        'builtin': True,
    },

    # ── Google Classroom templates ──
    {
        'id': 'gc_announcement', 'section': 'classroom',
        'name': 'General Announcement', 'category': 'announcement',
        'subject': 'Counselor\'s Corner — {{date}}',
        'body': (
            'Good morning, students!\n\n'
            'Here are a few important updates from the counseling office:\n\n'
            '1. [Update 1]\n'
            '2. [Update 2]\n'
            '3. [Update 3]\n\n'
            'As always, feel free to stop by or send me a message if you need anything.\n\n'
            '— {{counselor_name}}'
        ),
        'builtin': True,
    },
    {
        'id': 'gc_schedule_change', 'section': 'classroom',
        'name': 'Schedule Change Reminder', 'category': 'announcement',
        'subject': 'Schedule Change Reminder',
        'body': (
            'Heads up! There is a schedule change this week:\n\n'
            '[Describe the schedule change here]\n\n'
            'If you have any questions about how this affects your classes, '
            'come see me in the counseling office.\n\n'
            '— {{counselor_name}}'
        ),
        'builtin': True,
    },
    {
        'id': 'gc_college_deadline', 'section': 'classroom',
        'name': 'College/Career Deadline', 'category': 'college_career',
        'subject': 'Important Deadline Coming Up!',
        'body': (
            'Attention Seniors (and Juniors planning ahead)!\n\n'
            'An important deadline is approaching:\n\n'
            '[Deadline name]: [Date]\n'
            '[Brief description of what needs to be done]\n\n'
            'Key steps:\n'
            '- [Step 1]\n'
            '- [Step 2]\n'
            '- [Step 3]\n\n'
            'Need help? Sign up for a one-on-one meeting with me or come to '
            'the counseling office during lunch.\n\n'
            'Don\'t wait until the last minute!\n— {{counselor_name}}'
        ),
        'builtin': True,
    },
    {
        'id': 'gc_fafsa', 'section': 'classroom',
        'name': 'FAFSA Reminder', 'category': 'college_career',
        'subject': 'FAFSA Reminder — Free Money for College!',
        'body': (
            'Seniors! Have you completed your FAFSA yet?\n\n'
            'The FAFSA (Free Application for Federal Student Aid) is how you '
            'apply for financial aid including grants, scholarships, and work-study.\n\n'
            'What you need:\n'
            '- Your FSA ID (and your parent\'s FSA ID)\n'
            '- Social Security number\n'
            '- Tax information (IRS Data Retrieval Tool makes this easy)\n'
            '- List of schools you\'re applying to\n\n'
            'Apply at: studentaid.gov\n'
            'Our school code: [School Code]\n\n'
            'The counseling office is hosting FAFSA help sessions:\n'
            '[Date/Time]\n\n'
            'Don\'t leave free money on the table!\n— {{counselor_name}}'
        ),
        'builtin': True,
    },
    {
        'id': 'gc_scholarship', 'section': 'classroom',
        'name': 'Scholarship Spotlight', 'category': 'college_career',
        'subject': 'Scholarship Opportunity',
        'body': (
            'Scholarship Alert!\n\n'
            'Name: [Scholarship Name]\n'
            'Amount: [Dollar Amount]\n'
            'Deadline: [Date]\n'
            'Eligibility: [Brief requirements]\n\n'
            'How to apply:\n'
            '- [Step 1]\n'
            '- [Step 2]\n\n'
            'Link: [URL]\n\n'
            'Every scholarship you apply for increases your chances of reducing '
            'college costs. Even small scholarships add up!\n\n'
            'Come see me if you need help with your application.\n— {{counselor_name}}'
        ),
        'builtin': True,
    },
    {
        'id': 'gc_sel_checkin', 'section': 'classroom',
        'name': 'SEL Check-In', 'category': 'sel_wellness',
        'subject': 'Weekly Check-In',
        'body': (
            'Hey everyone,\n\n'
            'Taking a moment to check in with you all.\n\n'
            'On a scale of 1-5, how are you feeling today?\n'
            '1 = Really struggling\n'
            '2 = Having a tough time\n'
            '3 = Doing okay\n'
            '4 = Doing well\n'
            '5 = Feeling great!\n\n'
            'Remember: It\'s okay to not be okay. If you\'re at a 1 or 2, please '
            'reach out to me, a trusted adult, or text HOME to 741741 (Crisis Text Line).\n\n'
            'This week\'s wellness tip:\n'
            '[Tip about self-care, mindfulness, stress management, etc.]\n\n'
            '— {{counselor_name}}'
        ),
        'builtin': True,
    },
    {
        'id': 'gc_mindfulness', 'section': 'classroom',
        'name': 'Mindfulness Moment', 'category': 'sel_wellness',
        'subject': 'Mindfulness Moment',
        'body': (
            'Take a breath.\n\n'
            'Before you dive into your next assignment, let\'s take 60 seconds '
            'for ourselves.\n\n'
            'Try this:\n'
            '1. Close your eyes (or soften your gaze)\n'
            '2. Take 3 deep breaths — in through your nose, out through your mouth\n'
            '3. Notice how your body feels right now\n'
            '4. Set one intention for the rest of your day\n\n'
            'That\'s it. You just did something kind for yourself today.\n\n'
            '— {{counselor_name}}'
        ),
        'builtin': True,
    },
    {
        'id': 'gc_study_tips', 'section': 'classroom',
        'name': 'Study Tips', 'category': 'academic',
        'subject': 'Study Tips for Success',
        'body': (
            'With [exams/finals/midterms] coming up, here are some proven study strategies:\n\n'
            '1. Spaced practice — Study a little each day instead of cramming\n'
            '2. Active recall — Quiz yourself instead of re-reading notes\n'
            '3. Teach it — Explain concepts out loud or to a friend\n'
            '4. Take breaks — Use the Pomodoro technique (25 min study, 5 min break)\n'
            '5. Sleep — Your brain consolidates memory while you sleep!\n\n'
            'Need a quiet place to study? The counseling office has a study space '
            'available during lunch.\n\n'
            'You\'ve got this!\n— {{counselor_name}}'
        ),
        'builtin': True,
    },
    {
        'id': 'gc_test_prep', 'section': 'classroom',
        'name': 'Test Prep Reminder', 'category': 'academic',
        'subject': 'Testing Season — What You Need to Know',
        'body': (
            'Important testing information:\n\n'
            'Test: [SAT/AP/CAASPP/ACT]\n'
            'Date: [Date]\n'
            'Time: [Report time]\n'
            'Location: [Where to go]\n\n'
            'What to bring:\n'
            '- Photo ID\n'
            '- #2 pencils\n'
            '- Approved calculator (if applicable)\n'
            '- Snacks and water\n\n'
            'What NOT to bring:\n'
            '- Cell phones (must be off and stored)\n'
            '- Smart watches\n\n'
            'Tips: Get a good night\'s sleep, eat breakfast, and arrive early.\n\n'
            'Questions? Come see me!\n— {{counselor_name}}'
        ),
        'builtin': True,
    },

    # ── Newsletter templates ──
    {
        'id': 'nl_monthly', 'section': 'newsletter',
        'name': 'Monthly Counselor Newsletter', 'category': 'parent',
        'subject': 'Counselor Newsletter — {{date}}',
        'body': (
            'COUNSELOR\'S CORNER\n'
            '================================\n\n'
            'Dear Families,\n\n'
            'Welcome to this month\'s counselor newsletter! Here\'s what\'s '
            'happening:\n\n'
            'UPCOMING EVENTS\n'
            '- [Event 1]: [Date]\n'
            '- [Event 2]: [Date]\n'
            '- [Event 3]: [Date]\n\n'
            'IMPORTANT DEADLINES\n'
            '- [Deadline 1]: [Date]\n'
            '- [Deadline 2]: [Date]\n\n'
            'COUNSELOR TIP OF THE MONTH\n'
            '[Share a helpful tip for families about supporting their student]\n\n'
            'RESOURCES\n'
            '- [Resource 1]\n'
            '- [Resource 2]\n\n'
            'As always, please don\'t hesitate to reach out if you have questions '
            'or concerns about your student.\n\n'
            'Warm regards,\n{{counselor_name}}\nSchool Counselor'
        ),
        'builtin': True,
    },
    {
        'id': 'nl_event', 'section': 'newsletter',
        'name': 'Event Announcement', 'category': 'event',
        'subject': '[Event Name] — Save the Date!',
        'body': (
            'SAVE THE DATE!\n'
            '================================\n\n'
            '[Event Name]\n'
            'Date: [Date]\n'
            'Time: [Time]\n'
            'Location: [Location]\n\n'
            'What: [Brief description of the event]\n\n'
            'Who should attend: [Audience — students, parents, both?]\n\n'
            'What to expect:\n'
            '- [Detail 1]\n'
            '- [Detail 2]\n'
            '- [Detail 3]\n\n'
            'RSVP: [How to RSVP if needed]\n\n'
            'We look forward to seeing you there!\n\n'
            '{{counselor_name}}\nSchool Counselor'
        ),
        'builtin': True,
    },
    {
        'id': 'nl_college_night', 'section': 'newsletter',
        'name': 'College Night Invite', 'category': 'event',
        'subject': 'College & Career Night — You\'re Invited!',
        'body': (
            'COLLEGE & CAREER NIGHT\n'
            '================================\n\n'
            'Dear Families,\n\n'
            'You are invited to our annual College & Career Night!\n\n'
            'Date: [Date]\n'
            'Time: [Time]\n'
            'Location: [Location]\n\n'
            'What to expect:\n'
            '- College representatives and information tables\n'
            '- Financial aid and scholarship workshop\n'
            '- Career exploration activities\n'
            '- One-on-one Q&A with counselors\n\n'
            'This event is for students AND families. We encourage you to '
            'attend together!\n\n'
            'Light refreshments will be provided.\n\n'
            'See you there,\n{{counselor_name}}'
        ),
        'builtin': True,
    },

    # ── Quick Message templates ──
    {
        'id': 'qm_check_in', 'section': 'quick',
        'name': 'Quick Check-In', 'category': 'student',
        'subject': '',
        'body': (
            'Hi {{student_first_name}}! Just checking in — how are things going? '
            'Stop by my office if you need anything. — {{counselor_name}}'
        ),
        'builtin': True,
    },
    {
        'id': 'qm_meeting_reminder', 'section': 'quick',
        'name': 'Meeting Reminder', 'category': 'parent',
        'subject': '',
        'body': (
            'Hello {{parent_name}}, this is a reminder about our meeting '
            'scheduled for [Date/Time]. Please let me know if you need to '
            'reschedule. — {{counselor_name}}'
        ),
        'builtin': True,
    },
    {
        'id': 'qm_pass', 'section': 'quick',
        'name': 'Office Pass', 'category': 'student',
        'subject': '',
        'body': (
            'Hi {{student_first_name}}, please come see me in the counseling '
            'office when you have a chance today. — {{counselor_name}}'
        ),
        'builtin': True,
    },
    {
        'id': 'qm_congrats', 'section': 'quick',
        'name': 'Congratulations', 'category': 'student',
        'subject': '',
        'body': (
            'Hey {{student_first_name}}! I wanted to say congratulations on '
            '[achievement]. Keep up the great work! — {{counselor_name}}'
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
    if not os.path.exists(TEMPLATES_FILE):
        return []
    try:
        with open(TEMPLATES_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _write_custom_templates(templates):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(TEMPLATES_FILE, 'w') as f:
        json.dump(templates, f, indent=2, default=str)


def _all_templates():
    custom = _read_custom_templates()
    return DEFAULT_TEMPLATES + [t for t in custom
                                if t.get('counselor_id') == current_user.id]


def _merge(text, student, extra=None):
    if not text:
        return text
    replacements = {
        '{{student_first_name}}': student.first_name or '',
        '{{student_last_name}}': student.last_name or '',
        '{{student_full_name}}': student.full_name or '',
        '{{student_id}}': student.student_id_number or '',
        '{{grade_level}}': str(student.grade_level or ''),
        '{{parent_name}}': student.parent_guardian_name or '[Parent/Guardian]',
        '{{parent_email}}': student.parent_guardian_email or '',
        '{{counselor_name}}': current_user.display_name or current_user.username,
        '{{date}}': _date.today().strftime('%B %d, %Y'),
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
    students = (Student.query
                .filter_by(assigned_counselor_id=current_user.id, status='active')
                .order_by(Student.last_name, Student.first_name).all())
    templates = _all_templates()
    return render_template('email_drafts/index.html',
                           students=students, templates=templates,
                           sections=SECTIONS, merge_fields=MERGE_FIELDS)


@email_drafts_bp.route('/api/merge', methods=['POST'])
@csrf.exempt
@login_required
def api_merge():
    data = request.get_json(silent=True) or {}
    student_id = data.get('student_id')
    subject = data.get('subject', '')
    body = data.get('body', '')
    if student_id:
        student = Student.query.filter_by(
            id=student_id, assigned_counselor_id=current_user.id).first()
        if student:
            subject = _merge(subject, student, data.get('extra_fields'))
            body = _merge(body, student, data.get('extra_fields'))
    return jsonify({'subject': subject, 'body': body})


@email_drafts_bp.route('/api/ai-draft', methods=['POST'])
@csrf.exempt
@login_required
def api_ai_draft():
    from app.utils import ollama_client
    data = request.get_json(silent=True) or {}
    context = data.get('context', '')
    current_body = data.get('current_body', '')
    action = data.get('action', 'draft')
    section = data.get('section', 'email')

    if not ollama_client.is_available():
        return jsonify({'error': 'AI is not available. Make sure Ollama is running.'}), 503

    section_context = {
        'email': 'a professional email',
        'classroom': 'a Google Classroom post for students',
        'newsletter': 'a parent/family newsletter',
        'quick': 'a brief text-style message (under 50 words)',
    }
    tone = section_context.get(section, 'a professional message')

    if action == 'improve' and current_body:
        prompt = (
            f"Improve this {tone} from a school counselor. Keep the same intent "
            f"and any merge fields (like {{{{student_first_name}}}}).\n\n"
            f"Context: {context}\n\nOriginal:\n{current_body}"
        )
    else:
        length = '30 words' if section == 'quick' else '150 words'
        prompt = (
            f"Write {tone} from a school counselor.\n"
            f"Context: {context}\n"
            f"Use merge fields where appropriate: "
            f"{{{{student_first_name}}}}, {{{{parent_name}}}}, {{{{counselor_name}}}}, "
            f"{{{{grade_level}}}}, {{{{date}}}}.\n"
            f"Keep it warm but concise (under {length})."
        )

    system = (
        "You are a school counselor writing professional communications. "
        "Write clearly, warmly, and concisely. Use merge fields in double curly braces."
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
    data = request.get_json(silent=True) or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Template name is required'}), 400
    templates = _read_custom_templates()
    template = {
        'id': str(uuid.uuid4()),
        'counselor_id': current_user.id,
        'name': name,
        'section': data.get('section', 'email'),
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
    templates = _read_custom_templates()
    templates = [t for t in templates
                 if not (t['id'] == template_id
                         and t.get('counselor_id') == current_user.id)]
    _write_custom_templates(templates)
    return jsonify({'ok': True})
