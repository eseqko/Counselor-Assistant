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
from app.utils.stream_helpers import stream_sse
from app.utils.context_budget import budget_prompt
from app.utils.audit import log_action
from collections import defaultdict
from datetime import date, timedelta

ai_bp = Blueprint('ai', __name__)

COUNSELOR_SYSTEM_PROMPT = (
    "You are an experienced K-12 school counselor assistant. Give professional, "
    "actionable, ASCA-aligned feedback. Be concise. Use bullet points. Only "
    "reference provided information.\n\n"
    "IMPORTANT — interpret all academic data RELATIVE to the student's current "
    "grade level AND where they are in the school year. Credits, a-g areas, "
    "and course completion are cumulative; what's normal at the end of 10th "
    "grade is very different from 12th, and a 0 in Q1 means something very "
    "different from a 0 in Q4. When the prompt includes 'EXPECTED' or 'pace' "
    "labels, treat those as your benchmark. Assume students currently enrolled "
    "in (WIP) courses will pass them unless the data explicitly says otherwise; "
    "react to actual failures, not to in-progress credits that haven't posted "
    "yet. Reserve graduation-risk language for students explicitly flagged as "
    "behind pace for their grade and quarter, or for 11th-12th graders with "
    "credit/a-g deficits projected after WIP courses complete."
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

    prompt = f"""Review this counseling note and provide brief feedback.

{student_context}
Previous sessions:{notes_context or ' (first session)'}

Note: {note.note_type} | {note.session_date} | ASCA: {note.asca_domain or 'N/A'}
{note.content}
Follow-up: {'Yes' if note.follow_up_needed else 'No'}

Provide concise bullet points:
1. **Completeness** — Missing documentation?
2. **ASCA Alignment** — Correct domain?
3. **Follow-Up Suggestions** — Next steps?
4. **Tips** — Improvements for compliance?"""

    try:
        bp, bs = budget_prompt(prompt, COUNSELOR_SYSTEM_PROMPT)
        response = ollama_client.generate(bp, system=bs)
        log_action('ai_feedback', 'note', note.id, 'Generated AI feedback for note')
        return jsonify({'feedback': response})
    except Exception as e:
        return jsonify({'error': f'AI generation failed: {str(e)}'}), 500


@ai_bp.route('/note-feedback-stream', methods=['POST'])
@login_required
def note_feedback_stream():
    data = request.get_json()
    note_id = data.get('note_id')
    if not note_id:
        return jsonify({'error': 'Missing note_id'}), 400

    note = Note.query.get_or_404(note_id)
    student = note.student
    student_context = f"Student: Grade {student.grade_level or 'N/A'}"
    if student.iep_status:
        student_context += ", has IEP"
    if student.section_504:
        student_context += ", has 504 Plan"
    if student.el_status and student.el_status != 'EO':
        student_context += f", EL Status: {student.el_status}"

    recent_notes = Note.query.filter_by(
        student_id=student.id, author_id=current_user.id
    ).order_by(Note.session_date.desc()).limit(5).all()

    notes_context = ""
    for n in recent_notes:
        if n.id != note.id:
            notes_context += f"\n- {n.session_date}: {n.note_type} — {n.title or '(untitled)'}"

    prompt = f"""Review this counseling note and provide brief feedback.

{student_context}
Previous sessions:{notes_context or ' (first session)'}

Note: {note.note_type} | {note.session_date} | ASCA: {note.asca_domain or 'N/A'}
{note.content}
Follow-up: {'Yes' if note.follow_up_needed else 'No'}

Provide concise bullet points:
1. **Completeness** — Missing documentation?
2. **ASCA Alignment** — Correct domain?
3. **Follow-Up Suggestions** — Next steps?
4. **Tips** — Improvements for compliance?"""

    log_action('ai_feedback', 'note', note.id, 'Generated AI feedback for note')
    return stream_sse(prompt, system=COUNSELOR_SYSTEM_PROMPT)


_GRADE_NAMES = {
    6: '6th grader (middle school)', 7: '7th grader (middle school)',
    8: '8th grader (middle school)',
    9: '9th grader', 10: '10th grader', 11: '11th grader', 12: 'senior',
}


def _grade_name(n):
    return _GRADE_NAMES.get(n, f'Grade {n}' if n else 'unknown grade')


def _build_student_insights_prompt(student):
    """Build a compact insights prompt for a student, optimized for small LLMs.

    Frames credit and a-g progress relative to the student's grade level AND
    the quarter of the school year, so small models can't misread mid-career
    students as graduation risks based on absolute totals alone.
    """
    from app.routes.graduation import (expected_progress, projected_credits,
                                       pace_label)
    from app.utils.helpers import current_quarter, parse_transcript_quarter

    grade_name = _grade_name(student.grade_level)
    profile = grade_name
    designations = []
    if student.iep_status:
        designations.append("IEP")
    if student.section_504:
        designations.append("504")
    if student.el_status and student.el_status != 'EO':
        designations.append(f"EL:{student.el_display}")
    if designations:
        profile += f" | {', '.join(designations)}"

    notes = Note.query.filter_by(
        student_id=student.id, author_id=current_user.id
    ).order_by(Note.session_date.desc()).limit(5).all()

    notes_summary = ""
    note_types = defaultdict(int)
    for n in notes:
        note_types[n.note_type] += 1
        notes_summary += f"\n- {n.session_date} [{n.note_type}]: {n.content[:100]}"

    services = ServiceRecord.query.filter_by(
        student_id=student.id
    ).order_by(ServiceRecord.date.desc()).limit(5).all()

    services_summary = ""
    for s in services:
        services_summary += f"\n- {s.date} [{s.service_type}] {s.topic or ''}"

    overdue = Note.query.filter(
        Note.student_id == student.id,
        Note.follow_up_needed == True,
        Note.follow_up_date < date.today()
    ).count()

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
    att_context = ""
    if absences_30 or tardies_30:
        att_context = f"\nAttendance (30d): {absences_30} absent, {tardies_30} tardy"

    recent_grades = GradeRecord.query.filter_by(
        student_id=student.id
    ).order_by(GradeRecord.school_year.desc(), GradeRecord.quarter.desc()).limit(5).all()
    grades_context = ""
    if recent_grades:
        failing = [g for g in recent_grades if g.letter_grade in ('F', 'D', 'D-', 'D+', 'NP')]
        gpa_vals = [g.gpa_points for g in recent_grades if g.gpa_points is not None]
        avg_gpa = round(sum(gpa_vals) / len(gpa_vals), 2) if gpa_vals else 'N/A'
        grade_strs = [f"{g.course_name}:{g.letter_grade or 'N/A'}" for g in recent_grades]
        grades_context = f"\nGrades: GPA {avg_gpa}, {len(failing)} failing — {', '.join(grade_strs)}"

    # Quarter- and WIP-aware academic block. Prefers the transcript's own
    # reporting point; falls back to today's date if no transcript exists.
    transcript_context = ""
    latest_tr = student.transcript_records.first()
    quarter = current_quarter()
    if latest_tr and latest_tr.quarter:
        _, q_from_tr = parse_transcript_quarter(latest_tr.quarter)
        if q_from_tr:
            quarter = q_from_tr

    exp = expected_progress(student.grade_level, quarter=quarter)
    pace = None
    if exp and latest_tr:
        completed = int(latest_tr.total_completed or 0)
        wip = int(latest_tr.total_wip or 0)
        projected = projected_credits(completed, wip)
        pace = pace_label(completed, wip, student.grade_level, quarter=quarter)

        ag_met = latest_tr.ag_areas_met or 0
        wip_phrase = f"{completed} completed + {wip} WIP (projected {projected})" if wip else f"{completed} completed"
        pace_phrase = pace
        if pace not in ('pace unknown',) and wip > 0:
            pace_phrase = f"{pace} if current WIP courses pass"

        transcript_context = (
            f"\nAS OF: end of Q{quarter} of grade {student.grade_level}"
            f"\nEXPECTED BY THIS POINT: ~{exp['credits_expected']}/225 credits, "
            f"{exp['ag_expected_low']}-{exp['ag_expected_high']} of 7 a-g areas ({exp['ag_label']})"
            f"\nACTUAL: {wip_phrase} credits, {ag_met} of 7 a-g"
            f"\nPACE: {pace_phrase}"
        )

        # Credit gaps line: only emit when actually behind, or for upperclassmen
        # where the gap detail is always actionable. For on-pace 9-10 it's noise.
        should_show_gaps = (
            (student.grade_level or 0) >= 11
            or pace in ('behind pace', 'critically behind pace')
        )
        if should_show_gaps and latest_tr.credits_json:
            try:
                creds = json.loads(latest_tr.credits_json)
                gaps = []
                for subj, d in creds.items():
                    need = max(0, (d.get('required', 0) or 0) - (d.get('completed', 0) or 0))
                    if need > 0:
                        gaps.append(f"{subj}: need {int(need)}")
                if gaps:
                    transcript_context += f"\nCredit gaps: {', '.join(gaps)}"
            except (json.JSONDecodeError, TypeError):
                pass

        if latest_tr.ag_json:
            try:
                ag = json.loads(latest_tr.ag_json)
                deficient = [f"{d.get('label', a)}" for a, d in ag.items() if not d.get('isMet', False)]
                if deficient:
                    transcript_context += f"\na-g deficient: {', '.join(deficient)}"
            except (json.JSONDecodeError, TypeError):
                pass

    # Grade-conditional bullet 3 phrasing.
    if (student.grade_level or 0) >= 11:
        bullet_3 = ("3. **Graduation Status** — On track for spring graduation, "
                    "accounting for WIP courses? Specific credit gaps or a-g "
                    "deficiencies not covered by current enrollment?")
    else:
        bullet_3 = (f"3. **Graduation Progress** — Are credits and a-g on pace "
                    f"for {grade_name} at this point in the year? Any patterns "
                    f"to address now to stay on track for 12th?")

    return f"""Analyze this student and provide support recommendations.

STUDENT: {profile}
Notes: {len(notes)} | Services: {len(services)} | Overdue follow-ups: {overdue}{att_context}{grades_context}{transcript_context}

RECENT NOTES:{notes_summary or ' None'}
RECENT SERVICES:{services_summary or ' None'}

Provide concise bullet points for:
1. **Patterns** — Key themes in counseling history
2. **Risk Indicators** — Attendance, grades, or behavioral concerns
{bullet_3}
4. **Next Steps** — 3-5 specific, actionable interventions
{"5. **URGENT** — " + str(overdue) + " overdue follow-ups!" if overdue else ""}"""


@ai_bp.route('/student-insights', methods=['POST'])
@login_required
def student_insights():
    data = request.get_json()
    student_id = data.get('student_id')
    if not student_id:
        return jsonify({'error': 'Missing student_id'}), 400
    student = Student.query.get_or_404(student_id)
    prompt = _build_student_insights_prompt(student)
    try:
        bp, bs = budget_prompt(prompt, COUNSELOR_SYSTEM_PROMPT)
        response = ollama_client.generate(bp, system=bs)
        log_action('ai_feedback', 'student', student.id, 'Generated AI insights for student')
        return jsonify({'insights': response})
    except Exception as e:
        return jsonify({'error': f'AI generation failed: {str(e)}'}), 500


@ai_bp.route('/student-insights-stream', methods=['POST'])
@login_required
def student_insights_stream():
    data = request.get_json()
    student_id = data.get('student_id')
    if not student_id:
        return jsonify({'error': 'Missing student_id'}), 400
    student = Student.query.get_or_404(student_id)
    prompt = _build_student_insights_prompt(student)
    log_action('ai_feedback', 'student', student.id, 'Generated AI insights for student')
    return stream_sse(prompt, system=COUNSELOR_SYSTEM_PROMPT)


def _build_report_prompt(report_type, report_data):
    """Build the prompt for report insights. Returns prompt string or None."""
    if report_type == 'use_of_time':
        return _build_use_of_time_prompt(report_data)
    elif report_type == 'caseload_summary':
        return _build_caseload_prompt(report_data)
    elif report_type == 'topic_delivery':
        return _build_topic_delivery_prompt(report_data)
    elif report_type == 'early_warning':
        return _build_early_warning_prompt(report_data)
    elif report_type == 'cohort_trends':
        return _build_cohort_trends_prompt(report_data)
    return None


@ai_bp.route('/report-insights', methods=['POST'])
@login_required
def report_insights():
    data = request.get_json()
    report_type = data.get('report_type', '')
    report_data = data.get('report_data', {})
    if not report_type:
        return jsonify({'error': 'Missing report_type'}), 400
    prompt = _build_report_prompt(report_type, report_data)
    if prompt is None:
        return jsonify({'error': f'Unsupported report type: {report_type}'}), 400
    try:
        bp, bs = budget_prompt(prompt, COUNSELOR_SYSTEM_PROMPT)
        response = ollama_client.generate(bp, system=bs)
        log_action('ai_feedback', 'report', details=f'Generated AI insights for {report_type}')
        return jsonify({'insights': response})
    except Exception as e:
        return jsonify({'error': f'AI generation failed: {str(e)}'}), 500


@ai_bp.route('/report-insights-stream', methods=['POST'])
@login_required
def report_insights_stream():
    data = request.get_json()
    report_type = data.get('report_type', '')
    report_data = data.get('report_data', {})
    if not report_type:
        return jsonify({'error': 'Missing report_type'}), 400
    prompt = _build_report_prompt(report_type, report_data)
    if prompt is None:
        return jsonify({'error': f'Unsupported report type: {report_type}'}), 400
    log_action('ai_feedback', 'report', details=f'Generated AI insights for {report_type}')
    return stream_sse(prompt, system=COUNSELOR_SYSTEM_PROMPT)


def _build_use_of_time_prompt(data):
    time_by_type = data.get('time_by_type', {})
    total = data.get('total_minutes', 0)
    percentages = data.get('percentages', {})

    breakdown = "\n".join(
        f"- {stype}: {mins} min ({percentages.get(stype, 0)}%)"
        for stype, mins in time_by_type.items()
    )

    return f"""Analyze use-of-time report. ASCA recommends 80%+ direct/indirect services.

Total: {total} min
{breakdown or 'No data.'}

Provide concise bullet points:
1. **ASCA Alignment** — vs. 80/20 split?
2. **Imbalances** — Too much/little time anywhere?
3. **Action Items** — 2-3 specific changes"""


def _build_caseload_prompt(data):
    return f"""Analyze caseload. ASCA recommends 1:250 ratio.

Total: {data.get('total_students', 0)} | By grade: {data.get('by_grade', {})}
IEP: {data.get('iep_count', 0)} | 504: {data.get('section_504_count', 0)} | ELL: {data.get('ell_count', 0)}

Provide concise bullet points:
1. **Caseload Size** — Manageable?
2. **Equity** — Groups needing targeted support?
3. **Recommendations** — 2-3 proactive strategies"""


def _build_topic_delivery_prompt(data):
    topics = data.get('topic_counts', {})
    topic_lines = "\n".join(
        f"- {topic}: {info.get('count', 0)} sessions, {info.get('total_minutes', 0)} min, {info.get('students', 0)} students"
        for topic, info in topics.items()
    )

    return f"""Analyze topic delivery for ASCA domain coverage.

{topic_lines or 'No topics recorded.'}

Provide concise bullet points:
1. **Coverage** — All 3 ASCA domains covered?
2. **Gaps** — Missing topics?
3. **Suggestions** — 2-3 topics to add"""


def _build_early_warning_prompt(data):
    flagged = data.get('flagged', [])
    flagged_lines = ""
    for f in flagged:
        flagged_lines += f"\n- {f.get('name', '?')} (Grade {f.get('grade', '?')}, {f.get('severity', '?')}): {', '.join(f.get('flags', []))}"

    return f"""Analyze early warning report. Provide intervention recommendations.

Students: {data.get('total_students', 0)} | Critical: {data.get('critical', 0)} | Concern: {data.get('concern', 0)} | Watch: {data.get('watch', 0)}

Flagged:{flagged_lines or ' None'}

Provide concise bullet points:
1. **Priority Triage** — Who needs immediate intervention?
2. **Patterns** — Common themes across flagged students?
3. **Next Steps** — Top 3 actions this week"""


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

    return f"""Analyze cohort trends. {data.get('total_students', 0)} students.

Attendance by grade (90d): {att_lines or 'No data'}
Academics: {subj_lines or 'No data'}
Risk: {dict(risk_counts)} | a-g: {dict(ag_counts)}

Provide concise bullet points:
1. **Key Findings** — Significant trends?
2. **Grade-Level Patterns** — Which grades need most support?
3. **Recommendations** — 3-5 data-driven strategies"""


# =====================================================================
#  AI COURSE RECOMMENDATIONS (4x4 Schedule)
# =====================================================================

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


@ai_bp.route('/course-recommendations', methods=['POST'])
@login_required
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

    prompt = f"""Courses already selected from catalog. Write only explanations, not course lists.

Student: {student.display_name}, Grade {student.grade_level or 'N/A'} -> {next_grade}
Transcript: {transcript_summary}
Gaps: {credit_gap_lines}
Failed: {failed_lines}

Write:
1. **Priority Explanation** — 2-3 sentences on why these courses matter.
2. **Counselor Notes** — 2-3 bullet points to discuss with student/family."""

    try:
        bp, bs = budget_prompt(prompt, COUNSELOR_SYSTEM_PROMPT)
        ai_notes = ollama_client.generate(bp, system=bs)
        full_response = schedule_text + "\n\n" + ai_notes
        log_action('ai_feedback', 'student', student.id,
                   'Generated AI course recommendations')
        return jsonify({'recommendations': full_response})
    except Exception as e:
        # If AI fails, still return the code-generated schedule
        return jsonify({'recommendations': schedule_text + "\n\n*AI explanation unavailable.*"})
