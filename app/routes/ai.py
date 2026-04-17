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

    # --- Transcript context (detailed) ---
    transcript_context = ""
    latest_tr = student.transcript_records.first()
    if latest_tr:
        transcript_context = f"\n\nTRANSCRIPT: {int(latest_tr.total_completed)}/225 credits | Risk: {latest_tr.risk_level} | a-g: {latest_tr.ag_areas_met}/7 met ({latest_tr.ag_status}) | CTE: {latest_tr.cte_level}"
        if latest_tr.cte_is_completer:
            transcript_context += " (CTE Completer)"
        elif latest_tr.cte_completed:
            transcript_context += f" ({int(latest_tr.cte_completed)} CTE credits)"

        # Credit breakdown by subject area
        if latest_tr.credits_json:
            try:
                creds = json.loads(latest_tr.credits_json)
                credit_lines = []
                total_deficit = 0
                for subj, d in creds.items():
                    req = d.get('required', 0) or 0
                    comp = d.get('completed', 0) or 0
                    wip = d.get('wip', 0) or 0
                    need = max(0, req - comp)
                    status = 'MET' if need == 0 else f'NEED {int(need)} more'
                    credit_lines.append(f"  {subj}: {int(comp)}/{int(req)} credits ({status})" + (f" [WIP: {int(wip)}]" if wip else ""))
                    total_deficit += need
                if credit_lines:
                    transcript_context += f"\n\nCREDIT BREAKDOWN (Total deficit: {int(total_deficit)} credits):\n" + "\n".join(credit_lines)
            except (json.JSONDecodeError, TypeError):
                pass

        # a-g area details
        if latest_tr.ag_json:
            try:
                ag = json.loads(latest_tr.ag_json)
                met_areas = []
                deficient_areas = []
                for area, d in ag.items():
                    label = d.get('label', area)
                    if d.get('isMet', False):
                        met_areas.append(f"  Area {area} ({label}): MET")
                    else:
                        need = d.get('needed', 0)
                        deficient_areas.append(f"  Area {area} ({label}): DEFICIENT — need {int(need)} more")
                if deficient_areas or met_areas:
                    transcript_context += f"\n\na-g REQUIREMENTS ({len(met_areas)}/7 met):\n"
                    transcript_context += "\n".join(deficient_areas + met_areas)
            except (json.JSONDecodeError, TypeError):
                pass

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
4. **Transcript & Graduation Analysis** — Based on the credit breakdown, a-g status, and CTE pathway, is this student on track to graduate? What specific credit gaps or a-g deficiencies need immediate attention? What courses should be prioritized?
5. **Recommended Next Steps** — Specific, actionable interventions or follow-ups to consider, including academic planning based on transcript gaps.
{"6. **Overdue Follow-ups** — There are " + str(overdue) + " overdue follow-ups. Please flag this as urgent." if overdue else ""}

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
def build_recommended_schedule(student, target_grade_level=None,
                               exclude_course_numbers=None,
                               credit_gaps=None, ag_deficiencies=None):
    """Score and rank course picks for a target grade level.

    Returns (term1, term2, alternates, failed_course_names) where each of the
    first three is a list of (score, reasons, course).  Caller can override
    credit_gaps / ag_deficiencies for multi-year planning; when None they are
    computed from the student's transcript.
    """
    if target_grade_level is None:
        target_grade_level = (student.grade_level or 9) + 1
    if exclude_course_numbers is None:
        exclude_course_numbers = set()

    # --- Gather student needs (unless caller pre-computed) ---
    if credit_gaps is None or ag_deficiencies is None:
        latest_transcript = student.transcript_records.first()
        if credit_gaps is None:
            credit_gaps = {}
            if latest_transcript and latest_transcript.credits_json:
                try:
                    creds = json.loads(latest_transcript.credits_json)
                    for subj, d in creds.items():
                        req = d.get('required', 0) or 0
                        comp = d.get('completed', 0) or 0
                        need = max(0, req - comp)
                        if need > 0:
                            credit_gaps[subj.lower().strip()] = need
                except (json.JSONDecodeError, TypeError):
                    pass
        if ag_deficiencies is None:
            ag_deficiencies = {}
            if latest_transcript and latest_transcript.ag_json:
                try:
                    ag = json.loads(latest_transcript.ag_json)
                    for area, d in ag.items():
                        if not d.get('isMet', False):
                            ag_deficiencies[area] = {
                                'label': d.get('label', area),
                                'needed': d.get('needed', 0)
                            }
                except (json.JSONDecodeError, TypeError):
                    pass

    # Gather failed courses
    recent_grades = GradeRecord.query.filter_by(
        student_id=student.id
    ).order_by(GradeRecord.school_year.desc(), GradeRecord.quarter.desc()).all()

    failed_course_names = set()
    for g in recent_grades:
        if g.letter_grade in ('F', 'NP', 'I', 'W'):
            failed_course_names.add((g.course_name or '').strip())

    # --- Load catalog ---
    all_courses = Course.query.filter_by(is_active=True).order_by(Course.title).all()
    if not all_courses:
        return [], [], [], failed_course_names

    def course_fits_grade(course):
        if not course.grade_levels:
            return True
        return str(target_grade_level) in course.grade_levels

    def course_matches_subject(course, subject_keyword):
        keyword = subject_keyword.lower().strip()
        fields = [
            (course.department.name if course.department else ''),
            (course.subject_area or ''),
            (course.meets_requirement or ''),
            (course.title or ''),
        ]
        return any(keyword in f.lower() for f in fields)

    scored_courses = []

    for c in all_courses:
        if not course_fits_grade(c):
            continue
        if c.course_number and c.course_number in exclude_course_numbers:
            continue

        score = 0
        reasons = []

        for failed in failed_course_names:
            if failed.lower() in (c.title or '').lower() or (c.title or '').lower() in failed.lower():
                score += 100
                reasons.append(f"Retake of failed course: {failed}")
                break

        for gap_subject, credits_needed in credit_gaps.items():
            if course_matches_subject(c, gap_subject):
                score += 50 + credits_needed
                reasons.append(f"Fills {gap_subject} credit gap ({int(credits_needed)} credits needed)")
                break

        for area, info in ag_deficiencies.items():
            area_label = info['label'].lower()
            if course_matches_subject(c, area_label):
                score += 40
                reasons.append(f"Addresses a-g Area {area} ({info['label']}) deficiency")
                break

        if c.course_type == 'required':
            score += 20
            if not reasons:
                reasons.append("Required course")

        if c.meets_requirement:
            score += 10
            if not reasons:
                reasons.append(f"Meets graduation requirement: {c.meets_requirement}")

        if c.course_type == 'cte':
            score += 5
            if not reasons:
                reasons.append("CTE pathway course")

        if score == 0:
            score = 1
            reasons.append("Elective option")

        scored_courses.append((score, reasons, c))

    scored_courses.sort(key=lambda x: x[0], reverse=True)

    selected = scored_courses[:8]
    alternates = scored_courses[8:12]
    term1 = selected[:4]
    term2 = selected[4:8]

    return term1, term2, alternates, failed_course_names


def course_recommendations():
    """Generate AI-powered course recommendations for next year based on transcript and grades."""
    data = request.get_json()
    student_id = data.get('student_id')
    if not student_id:
        return jsonify({'error': 'Missing student_id'}), 400

    student = Student.query.get_or_404(student_id)

    term1, term2, alternates, failed_course_names = build_recommended_schedule(student)

    if not term1 and not term2:
        return jsonify({
            'recommendations': '',
            'empty_catalog': True,
            'empty_message': (
                'No courses found in the Course Catalog. '
                'Please add courses before generating recommendations. '
                'The AI needs real course data to make accurate suggestions.'
            )
        })

    selected = list(term1) + list(term2)
    next_grade = (student.grade_level or 9) + 1

    def format_course_line(rank, item):
        score, reasons, c = item
        dept = c.department.name if c.department else 'N/A'
        credits = int(c.credits) if c.credits else 5
        reason_str = reasons[0] if reasons else ''
        return f"* **{dept}: {c.title} ({c.course_number})** — {credits} credits\n    + Why it's recommended: {reason_str}"

    lines = []
    lines.append(f"Here's a recommended 8-class schedule for {student.display_name}:\n")
    lines.append("**TERM 1 (Q1-Q2): 4 Courses**\n")
    for i, item in enumerate(term1):
        lines.append(format_course_line(i + 1, item))
    lines.append("\n**TERM 2 (Q3-Q4): 4 Courses**\n")
    for i, item in enumerate(term2):
        lines.append(format_course_line(i + 5, item))

    if alternates:
        lines.append("\n**Alternative Options:**\n")
        for item in alternates:
            _, reasons, c = item
            dept = c.department.name if c.department else 'N/A'
            lines.append(f"* {dept}: {c.title} ({c.course_number}) — {reasons[0] if reasons else 'Elective'}")

    schedule_text = "\n".join(lines)

    # --- Build context for AI to add explanations ---
    transcript_summary = "No transcript data available."
    if latest_transcript:
        transcript_summary = (
            f"Credits: {int(latest_transcript.total_completed)}/225 completed"
            f" | a-g: {latest_transcript.ag_areas_met}/7 met ({latest_transcript.ag_status})"
            f" | Risk: {latest_transcript.risk_level}"
        )
    credit_gap_lines = "\n".join(
        f"  {subj}: need {int(need)} more credits"
        for subj, need in credit_gaps.items()
    ) if credit_gaps else "  None"
    failed_lines = "\n  ".join(failed_course_names) if failed_course_names else "None"

    prompt = f"""You are a school counselor assistant. I have already selected courses from the school's actual catalog for a student. Your job is to write a brief Priority Explanation and Counselor Notes section ONLY.

Do NOT list courses or suggest different courses. The courses have already been chosen. Just explain the priority reasoning and add counselor notes.

STUDENT: {student.display_name}, Grade {student.grade_level or 'N/A'} (will be Grade {next_grade} next year)
Transcript: {transcript_summary}
Credit Gaps:
{credit_gap_lines}
Failed Courses: {failed_lines}

SELECTED SCHEDULE:
{schedule_text}

Write exactly two sections:
1. **Priority Explanation** — 2-3 sentences on why these courses are prioritized in this order and what's at stake.
2. **Counselor Notes** — 2-3 bullet points of flags for the counselor to discuss with the student/family."""

    try:
        ai_notes = ollama_client.generate(prompt, system=COUNSELOR_SYSTEM_PROMPT)
        # Combine the code-generated schedule with AI explanations
        full_response = schedule_text + "\n\n" + ai_notes
        log_action('ai_feedback', 'student', student.id,
                   'Generated AI course recommendations')
        return jsonify({'recommendations': full_response})
    except Exception as e:
        # If AI fails, still return the code-generated schedule
        return jsonify({'recommendations': schedule_text + "\n\n*AI explanation unavailable.*"})
