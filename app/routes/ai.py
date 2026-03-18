"""AI Assistant routes — powered by local Ollama LLM (FERPA safe)."""
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.note import Note
from app.models.student import Student
from app.models.service_record import ServiceRecord
from app.models.activity import Activity
from app.utils import ollama_client
from app.utils.audit import log_action
from collections import defaultdict
from datetime import date, timedelta

ai_bp = Blueprint('ai', __name__)

COUNSELOR_SYSTEM_PROMPT = (
    "You are an experienced school counselor assistant. You are helping a school counselor "
    "review their notes, student data, and reports. Your feedback should be professional, "
    "actionable, and aligned with ASCA National Model standards. Keep responses concise and "
    "practical. Never generate fictional student data. Only reference information provided to you. "
    "Use bullet points for clarity."
)


@ai_bp.route('/status')
@login_required
def status():
    """Check if Ollama is available and return model info."""
    available = ollama_client.is_available()
    return jsonify({
        'available': available,
        'model': ollama_client.get_model(),
        'base_url': ollama_client.get_base_url(),
        'models': ollama_client.list_models() if available else [],
    })


@ai_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """Get or update Ollama settings."""
    if request.method == 'POST':
        data = request.get_json()
        base_url = data.get('base_url', '').strip().rstrip('/')
        model = data.get('model', '').strip()
        if base_url:
            ollama_client.save_settings(base_url, model or ollama_client.OLLAMA_MODEL)
        return jsonify({'saved': True})

    return jsonify({
        'base_url': ollama_client.get_base_url(),
        'model': ollama_client.get_model(),
    })


@ai_bp.route('/note-feedback', methods=['POST'])
@login_required
def note_feedback():
    """Generate feedback on a counseling note."""
    data = request.get_json()
    note_id = data.get('note_id')
    if not note_id:
        return jsonify({'error': 'Missing note_id'}), 400

    note = Note.query.get_or_404(note_id)

    # Build context about the student
    student = note.student
    student_context = (
        f"Student: Grade {student.grade_level or 'N/A'}"
    )
    if student.iep_status:
        student_context += ", has IEP"
    if student.section_504:
        student_context += ", has 504 Plan"
    if student.el_status and student.el_status != 'EO':
        student_context += f", EL Status: {student.el_status}"

    # Get recent notes for context
    recent_notes = Note.query.filter_by(
        student_id=student.id, author_id=current_user.id
    ).order_by(Note.session_date.desc()).limit(5).all()

    notes_context = ""
    for n in recent_notes:
        if n.id != note.id:
            notes_context += f"\n- {n.session_date}: {n.note_type} — {n.title or '(untitled)'}"

    prompt = f"""Review this counseling session note and provide feedback.

{student_context}
Previous sessions with this student:{notes_context or ' (first session)'}

--- CURRENT NOTE ---
Type: {note.note_type}
Date: {note.session_date}
Title: {note.title or '(untitled)'}
ASCA Domain: {note.asca_domain or 'Not specified'}
Duration: {note.duration_minutes or 'N/A'} minutes
Delivery: {note.delivery_method or 'N/A'}
Content:
{note.content}

Follow-up needed: {'Yes' if note.follow_up_needed else 'No'}
{('Follow-up notes: ' + note.follow_up_notes) if note.follow_up_notes else ''}
--- END NOTE ---

Please provide:
1. **Completeness Check** — Is any important documentation missing?
2. **ASCA Alignment** — Does the domain ({note.asca_domain or 'not specified'}) match the content? Suggest if wrong.
3. **Follow-Up Suggestions** — Based on the note content, what follow-up actions or interventions might be appropriate?
4. **Documentation Tips** — Any improvements to make the note more thorough for compliance purposes?

Keep your response concise and actionable."""

    try:
        response = ollama_client.generate(prompt, system=COUNSELOR_SYSTEM_PROMPT)
        log_action('ai_feedback', 'note', note.id, 'Generated AI feedback for note')
        return jsonify({'feedback': response})
    except Exception as e:
        return jsonify({'error': f'AI generation failed: {str(e)}'}), 500


@ai_bp.route('/student-insights', methods=['POST'])
@login_required
def student_insights():
    """Generate support insights for a student based on their service history."""
    data = request.get_json()
    student_id = data.get('student_id')
    if not student_id:
        return jsonify({'error': 'Missing student_id'}), 400

    student = Student.query.get_or_404(student_id)

    # Gather student profile
    profile = f"Grade {student.grade_level or 'N/A'}"
    designations = []
    if student.iep_status:
        designations.append("IEP")
    if student.section_504:
        designations.append("504 Plan")
    if student.el_status and student.el_status != 'EO':
        designations.append(f"EL: {student.el_display}")
    if designations:
        profile += f" | Designations: {', '.join(designations)}"

    tags = [t.name for t in student.tags]
    if tags:
        profile += f" | Tags: {', '.join(tags)}"

    # Recent notes summary
    notes = Note.query.filter_by(
        student_id=student.id, author_id=current_user.id
    ).order_by(Note.session_date.desc()).limit(10).all()

    notes_summary = ""
    note_types = defaultdict(int)
    domains = defaultdict(int)
    for n in notes:
        note_types[n.note_type] += 1
        if n.asca_domain:
            domains[n.asca_domain] += 1
        notes_summary += f"\n- {n.session_date} [{n.note_type}] {n.title or ''}: {n.content[:150]}"

    # Service records
    services = ServiceRecord.query.filter_by(
        student_id=student.id
    ).order_by(ServiceRecord.date.desc()).limit(10).all()

    services_summary = ""
    for s in services:
        services_summary += f"\n- {s.date} [{s.service_type}] {s.topic or ''}: {s.description[:100] if s.description else 'N/A'}"
        if s.outcome:
            services_summary += f" (Outcome: {s.outcome[:80]})"

    # Check for overdue follow-ups
    overdue = Note.query.filter(
        Note.student_id == student.id,
        Note.follow_up_needed == True,
        Note.follow_up_date < date.today()
    ).count()

    prompt = f"""Analyze this student's counseling history and provide support recommendations.

STUDENT PROFILE: {profile}
Total notes: {len(notes)} | Total services: {len(services)}
Note types used: {dict(note_types)}
ASCA domains covered: {dict(domains)}
Overdue follow-ups: {overdue}

RECENT NOTES:{notes_summary or ' None'}

RECENT SERVICES:{services_summary or ' None'}

Please provide:
1. **Patterns & Observations** — What themes or patterns do you notice in this student's counseling history?
2. **Gaps in Service** — Are any ASCA domains underserved? Any missing service types that might benefit this student?
3. **Risk Indicators** — Based on the notes, are there any concerns that should be flagged?
4. **Recommended Next Steps** — Specific, actionable interventions or follow-ups to consider.
{"5. **Overdue Follow-ups** — There are " + str(overdue) + " overdue follow-ups. Please flag this as urgent." if overdue else ""}

Keep recommendations practical and ASCA-aligned."""

    try:
        response = ollama_client.generate(prompt, system=COUNSELOR_SYSTEM_PROMPT)
        log_action('ai_feedback', 'student', student.id, 'Generated AI insights for student')
        return jsonify({'insights': response})
    except Exception as e:
        return jsonify({'error': f'AI generation failed: {str(e)}'}), 500


@ai_bp.route('/report-insights', methods=['POST'])
@login_required
def report_insights():
    """Generate AI insights for a report."""
    data = request.get_json()
    report_type = data.get('report_type', '')
    report_data = data.get('report_data', {})

    if not report_type:
        return jsonify({'error': 'Missing report_type'}), 400

    if report_type == 'use_of_time':
        prompt = _build_use_of_time_prompt(report_data)
    elif report_type == 'caseload_summary':
        prompt = _build_caseload_prompt(report_data)
    elif report_type == 'topic_delivery':
        prompt = _build_topic_delivery_prompt(report_data)
    else:
        return jsonify({'error': f'Unsupported report type: {report_type}'}), 400

    try:
        response = ollama_client.generate(prompt, system=COUNSELOR_SYSTEM_PROMPT)
        log_action('ai_feedback', 'report', details=f'Generated AI insights for {report_type}')
        return jsonify({'insights': response})
    except Exception as e:
        return jsonify({'error': f'AI generation failed: {str(e)}'}), 500


def _build_use_of_time_prompt(data):
    time_by_type = data.get('time_by_type', {})
    total = data.get('total_minutes', 0)
    percentages = data.get('percentages', {})

    breakdown = "\n".join(
        f"- {stype}: {mins} min ({percentages.get(stype, 0)}%)"
        for stype, mins in time_by_type.items()
    )

    return f"""Analyze this counselor's use-of-time report and provide recommendations.

ASCA recommends counselors spend 80%+ of time in direct/indirect student services.

TIME BREAKDOWN (Total: {total} minutes):
{breakdown or 'No data available.'}

Please provide:
1. **ASCA Alignment** — How does this time distribution compare to ASCA's recommended 80/20 split (direct+indirect services vs. program management/non-counseling)?
2. **Imbalances** — Any areas getting too much or too little time?
3. **Efficiency Tips** — Suggestions to optimize time toward student-facing activities.
4. **Action Items** — 2-3 specific changes to consider for the next reporting period.

Be specific with percentages and comparisons to ASCA standards."""


def _build_caseload_prompt(data):
    return f"""Analyze this caseload summary and provide equity/support insights.

CASELOAD DEMOGRAPHICS:
- Total students: {data.get('total_students', 0)}
- By grade: {data.get('by_grade', {})}
- By gender: {data.get('by_gender', {})}
- By ethnicity: {data.get('by_ethnicity', {})}
- IEP students: {data.get('iep_count', 0)}
- 504 Plan students: {data.get('section_504_count', 0)}
- ELL students: {data.get('ell_count', 0)}

ASCA recommends a ratio of 1:250 (counselor to students).

Please provide:
1. **Caseload Size** — Is this caseload manageable per ASCA guidelines?
2. **Equity Considerations** — Are there demographic groups that may need targeted support or outreach?
3. **Special Populations** — With {data.get('iep_count', 0)} IEP, {data.get('section_504_count', 0)} 504, and {data.get('ell_count', 0)} ELL students, what considerations should the counselor keep in mind?
4. **Recommendations** — Suggest 2-3 proactive strategies based on this caseload composition."""


def _build_topic_delivery_prompt(data):
    topics = data.get('topic_counts', {})
    topic_lines = "\n".join(
        f"- {topic}: {info.get('count', 0)} sessions, {info.get('total_minutes', 0)} min, {info.get('students', 0)} students"
        for topic, info in topics.items()
    )

    return f"""Analyze this topic delivery report and provide coverage insights.

TOPICS DELIVERED:
{topic_lines or 'No topics recorded.'}

Please provide:
1. **Coverage Analysis** — Are all three ASCA domains (Academic, Career, Social/Emotional) adequately covered?
2. **Gaps** — What important counseling topics appear to be missing or underrepresented?
3. **Student Reach** — Are sessions reaching enough students? Any topics where small-group or classroom delivery might increase impact?
4. **Suggestions** — Recommend 2-3 topics or activities to add based on common school counseling needs."""
