"""AI Assistant routes — powered by local Ollama LLM (FERPA safe)."""
import json
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.note import Note
from app.models.student import Student
from app.models.service_record import ServiceRecord
from app.models.activity import Activity
from app.models.attendance import AttendanceRecord
from app.models.grade import GradeRecord
from app.models.transcript import TranscriptRecord
from app.models.course import Course, Department, GraduationRequirement
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

    # --- Attendance data ---
    thirty_days_ago = date.today() - timedelta(days=30)
    absences_30 = AttendanceRecord.query.filter(
        AttendanceRecord.student_id == student.id,
        AttendanceRecord.date >= thirty_days_ago,
        AttendanceRecord.status == 'absent'
    ).count()
    tardies_30 = AttendanceRecord.query.filter(
        AttendanceRecord.student_id == student.id,
        AttendanceRecord.date >= thirty_days_ago,
        AttendanceRecord.status == 'tardy'
    ).count()
    total_att = AttendanceRecord.query.filter(
        AttendanceRecord.student_id == student.id,
        AttendanceRecord.date >= thirty_days_ago
    ).count()
    att_context = ""
    if total_att > 0:
        present = total_att - absences_30 - tardies_30
        att_rate = round(present / total_att * 100, 1)
        att_context = f"\n\nATTENDANCE (Last 30 days): {total_att} records | {absences_30} absences, {tardies_30} tardies | Rate: {att_rate}%"

    # --- Grades data ---
    recent_grades = GradeRecord.query.filter_by(
        student_id=student.id
    ).order_by(GradeRecord.school_year.desc(), GradeRecord.quarter.desc()).limit(8).all()
    grades_context = ""
    if recent_grades:
        grade_lines = []
        for g in recent_grades:
            grade_lines.append(f"  {g.course_name}: {g.letter_grade or 'N/A'} (Q{g.quarter or '?'} {g.school_year or ''})")
        failing = [g for g in recent_grades if g.letter_grade in ('F', 'D', 'D-', 'D+', 'NP')]
        gpa_vals = [g.gpa_points for g in recent_grades if g.gpa_points is not None]
        avg_gpa = round(sum(gpa_vals) / len(gpa_vals), 2) if gpa_vals else 'N/A'
        grades_context = f"\n\nGRADES (Most Recent): Avg GPA: {avg_gpa} | Failing: {len(failing)}\n" + "\n".join(grade_lines)

    # --- Transcript context ---
    transcript_context = ""
    latest_tr = student.transcript_records.first()
    if latest_tr:
        transcript_context = f"\n\nTRANSCRIPT: {int(latest_tr.total_completed)}/225 credits | Risk: {latest_tr.risk_level} | a-g: {latest_tr.ag_areas_met}/7 met ({latest_tr.ag_status}) | CTE: {latest_tr.cte_level}"

    prompt = f"""Analyze this student's counseling history and provide support recommendations.

STUDENT PROFILE: {profile}
Total notes: {len(notes)} | Total services: {len(services)}
Note types used: {dict(note_types)}
ASCA domains covered: {dict(domains)}
Overdue follow-ups: {overdue}{att_context}{grades_context}{transcript_context}

RECENT NOTES:{notes_summary or ' None'}

RECENT SERVICES:{services_summary or ' None'}

Please provide:
1. **Patterns & Observations** — What themes or patterns do you notice in this student's counseling history?
2. **Gaps in Service** — Are any ASCA domains underserved? Any missing service types that might benefit this student?
3. **Risk Indicators** — Based on the notes, attendance, and grades, are there any concerns that should be flagged?
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
    elif report_type == 'early_warning':
        prompt = _build_early_warning_prompt(report_data)
    elif report_type == 'cohort_trends':
        prompt = _build_cohort_trends_prompt(report_data)
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


def _build_early_warning_prompt(data):
    flagged = data.get('flagged', [])
    flagged_lines = ""
    for f in flagged:
        flagged_lines += f"\n- {f.get('name', '?')} (Grade {f.get('grade', '?')}, {f.get('severity', '?')}): {', '.join(f.get('flags', []))}"

    return f"""Analyze this early warning report and provide intervention recommendations.

CASELOAD: {data.get('total_students', 0)} total students
FLAGGED: {data.get('critical', 0)} Critical, {data.get('concern', 0)} Concern, {data.get('watch', 0)} Watch

FLAGGED STUDENTS:{flagged_lines or ' None'}

Please provide:
1. **Priority Triage** — Which students need immediate intervention? Rank by urgency.
2. **Pattern Analysis** — Do you see any common themes (attendance, grades, crisis) across flagged students?
3. **Intervention Strategies** — For each severity level (Critical, Concern, Watch), suggest specific counselor actions.
4. **Systemic Issues** — Are there grade-level or demographic patterns that suggest a systemic issue needing schoolwide intervention?
5. **Next Steps** — Top 3 actions the counselor should take this week.

Be specific and actionable. Reference ASCA and MTSS frameworks where appropriate."""


def _build_cohort_trends_prompt(data):
    att_by_grade = data.get('att_rates_by_grade', {})
    subject_stats = data.get('subject_stats', {})
    risk_counts = data.get('risk_counts', {})
    ag_counts = data.get('ag_counts', {})

    att_lines = "\n".join(f"  Grade {g}: {r}%" for g, r in att_by_grade.items())
    subj_lines = "\n".join(
        f"  {s}: {d.get('pass_rate', 0)}% pass rate, GPA {d.get('avg_gpa', 'N/A')}, {d.get('failing', 0)} failing"
        for s, d in subject_stats.items()
    )

    return f"""Analyze these cohort-wide trends and provide strategic recommendations.

CASELOAD: {data.get('total_students', 0)} students

ATTENDANCE RATES BY GRADE (last 90 days):
{att_lines or '  No data'}

ACADEMIC PERFORMANCE BY SUBJECT:
{subj_lines or '  No data'}

GRADUATION RISK: {dict(risk_counts)}
A-G STATUS: {dict(ag_counts)}

Please provide:
1. **Key Findings** — What are the most significant trends or concerns?
2. **Grade-Level Patterns** — Which grade levels need the most support? Why?
3. **Subject Area Concerns** — Which subjects have the lowest pass rates and what interventions might help?
4. **Equity Lens** — Are certain student populations likely being underserved based on these patterns?
5. **Schoolwide Recommendations** — 3-5 data-driven strategies for improving outcomes across the caseload.
6. **Data Gaps** — What additional data would help paint a clearer picture?

Ground your analysis in ASCA and MTSS frameworks."""


# =====================================================================
#  AI COURSE RECOMMENDATIONS (4x4 Schedule)
# =====================================================================

@ai_bp.route('/course-recommendations', methods=['POST'])
@login_required
def course_recommendations():
    """Generate AI-powered course recommendations for next year based on transcript and grades."""
    data = request.get_json()
    student_id = data.get('student_id')
    if not student_id:
        return jsonify({'error': 'Missing student_id'}), 400

    student = Student.query.get_or_404(student_id)

    # Gather transcript data
    latest_transcript = student.transcript_records.first()
    transcript_info = "No transcript data available."
    credits_detail = ""
    ag_detail = ""
    if latest_transcript:
        transcript_info = (
            f"Credits: {int(latest_transcript.total_completed)}/225 completed"
            f" | WIP: {int(latest_transcript.total_wip or 0)}"
            f" | Risk: {latest_transcript.risk_level}"
            f" | a-g: {latest_transcript.ag_areas_met}/7 met ({latest_transcript.ag_status})"
            f" | CTE: {latest_transcript.cte_completed} credits ({latest_transcript.cte_level})"
        )
        if latest_transcript.credits_json:
            try:
                creds = json.loads(latest_transcript.credits_json)
                lines = []
                for subj, d in creds.items():
                    req = d.get('required', 0) or 0
                    comp = d.get('completed', 0) or 0
                    need = max(0, req - comp)
                    if need > 0:
                        lines.append(f"  {subj}: need {int(need)} more credits ({int(comp)}/{int(req)})")
                if lines:
                    credits_detail = "\n\nGRADUATION CREDIT GAPS:\n" + "\n".join(lines)
            except (json.JSONDecodeError, TypeError):
                pass
        if latest_transcript.ag_json:
            try:
                ag = json.loads(latest_transcript.ag_json)
                lines = []
                for area, d in ag.items():
                    if not d.get('isMet', False):
                        need = d.get('needed', 0)
                        label = d.get('label', area)
                        lines.append(f"  Area {area} ({label}): need {int(need)} more")
                if lines:
                    ag_detail = "\n\na-g DEFICIENCIES:\n" + "\n".join(lines)
            except (json.JSONDecodeError, TypeError):
                pass

    # Gather recent grades
    recent_grades = GradeRecord.query.filter_by(
        student_id=student.id
    ).order_by(GradeRecord.school_year.desc(), GradeRecord.quarter.desc()).all()

    grade_lines = ""
    completed_courses = set()
    failed_courses = []
    for g in recent_grades:
        completed_courses.add(g.course_name)
        status = g.letter_grade or 'N/A'
        grade_lines += f"\n  {g.course_name} ({g.subject_area or 'N/A'}): {status} — Q{g.quarter or '?'} {g.school_year or ''}"
        if g.letter_grade in ('F', 'NP', 'I', 'W'):
            failed_courses.append(g.course_name)

    failed_info = ""
    if failed_courses:
        failed_info = f"\n\nFAILED/INCOMPLETE COURSES (may need to retake):\n  " + "\n  ".join(set(failed_courses))

    # Gather available courses from catalog
    courses = Course.query.filter_by(is_active=True).order_by(Course.title).all()
    catalog_info = ""
    if courses:
        dept_courses = defaultdict(list)
        for c in courses:
            dept = c.department.name if c.department else 'Other'
            grade_levels = c.grade_levels or ''
            meets = c.meets_requirement or ''
            ctype = c.course_type or ''
            dept_courses[dept].append(
                f"    {c.title} ({c.course_number}) — {ctype}, grades: {grade_levels}, satisfies: {meets}"
            )
        catalog_lines = []
        for dept, clist in sorted(dept_courses.items()):
            catalog_lines.append(f"\n  [{dept}]")
            catalog_lines.extend(clist[:15])  # Limit per department
        catalog_info = "\n\nAVAILABLE COURSES (from Course Catalog):" + "\n".join(catalog_lines)

    # Graduation requirements
    grad_reqs = GraduationRequirement.query.order_by(GraduationRequirement.sort_order).all()
    req_info = ""
    if grad_reqs:
        req_lines = [f"  {r.name}: {r.credits_required} credits" for r in grad_reqs]
        req_info = "\n\nGRADUATION REQUIREMENTS:\n" + "\n".join(req_lines)

    prompt = f"""You are helping a school counselor plan next year's schedule for a student.

IMPORTANT: This school uses a 4x4 BELL SCHEDULE:
- 4 classes per quarter, each worth 5 credits
- Quarters 1 & 2 = Term 1 (Semester 1 classes)
- Quarters 3 & 4 = Term 2 (Semester 2 classes)
- Students take 8 different classes per year (4 per term)
- Classes change after Quarter 2

STUDENT: {student.display_name}, Grade {student.grade_level or 'N/A'} (will be Grade {(student.grade_level or 9) + 1} next year)
Designations: {'IEP' if student.iep_status else ''} {'504' if student.section_504 else ''} {student.el_display if student.el_status != 'EO' else ''}

TRANSCRIPT SUMMARY: {transcript_info}{credits_detail}{ag_detail}

COURSE HISTORY:{grade_lines or ' No grades on file'}{failed_info}{req_info}{catalog_info}

Based on this student's transcript gaps, a-g deficiencies, failed courses, and graduation requirements, recommend a full 8-class schedule for next year.

Please provide:
1. **TERM 1 (Q1-Q2): 4 Courses**
   - For each: Course name, why it's recommended, what requirement it fills
   - Prioritize: failed course retakes, graduation gaps, a-g deficiencies

2. **TERM 2 (Q3-Q4): 4 Courses**
   - For each: Course name, why it's recommended, what requirement it fills

3. **Priority Explanation** — Why these courses in this order? What's at stake if not taken?

4. **Alternative Options** — For each term, suggest 1-2 swap options if a course is unavailable.

5. **Counselor Notes** — Any flags the counselor should discuss with the student/family (e.g., course load concerns, need for summer school, etc.)

Be specific. Reference actual credit gaps and graduation requirements. If the student has failed courses, prioritize retakes."""

    try:
        response = ollama_client.generate(prompt, system=COUNSELOR_SYSTEM_PROMPT)
        log_action('ai_feedback', 'student', student.id,
                   'Generated AI course recommendations')
        return jsonify({'recommendations': response})
    except Exception as e:
        return jsonify({'error': f'AI generation failed: {str(e)}'}), 500
