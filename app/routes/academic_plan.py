"""4-Year Academic Plan Builder — multi-year course sequencing with AI auto-fill."""
import json
from collections import defaultdict
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from app import db, csrf
from app.models.student import Student
from app.models.academic_plan import AcademicPlan
from app.models.grade import GradeRecord
from app.models.course import Course
from app.routes.graduation import (
    _compute_credits_from_grades, _compute_ag_from_grades,
    _risk_level, GRAD_REQUIREMENTS, AG_REQUIREMENTS, TOTAL_REQUIRED,
    _SUBJECT_MAP,
)
from app.routes.ai import build_recommended_schedule
from app.utils.audit import log_action

academic_plan_bp = Blueprint('academic_plan', __name__)

CURRENT_SCHOOL_YEAR = '2025-2026'
SLOTS_PER_TERM = 4


def _empty_slot(slot_num):
    return {
        'slot': slot_num, 'course_number': '', 'course_title': '',
        'credits': 5, 'subject_area': '', 'is_ag': False,
        'letter_grade': '', 'source': 'empty',
    }


def _grade_for_school_year(student, school_year):
    """Infer grade level for a past school year based on current grade."""
    if not school_year or not student.grade_level:
        return None
    try:
        start_year = int(school_year.split('-')[0])
        current_start = int(CURRENT_SCHOOL_YEAR.split('-')[0])
        offset = current_start - start_year
        return student.grade_level - offset
    except (ValueError, IndexError):
        return None


def _build_grid(student):
    """Build the 4-year grid: historical from GradeRecords, planned from AcademicPlan."""
    grid = {}
    for gl in range(9, 13):
        grid[gl] = {
            'term1': [_empty_slot(i) for i in range(SLOTS_PER_TERM)],
            'term2': [_empty_slot(i) for i in range(SLOTS_PER_TERM)],
            'is_historical': False,
            'is_current': False,
            'is_planned': False,
        }

    grades = GradeRecord.query.filter_by(student_id=student.id).order_by(
        GradeRecord.school_year.desc(), GradeRecord.quarter.desc()
    ).all()

    # Group by school_year, pick latest quarter per course
    by_year = defaultdict(dict)
    for g in grades:
        key = (g.course_name or '', g.period or 0)
        if key not in by_year[g.school_year]:
            by_year[g.school_year][key] = g

    for school_year, courses in by_year.items():
        gl = _grade_for_school_year(student, school_year)
        if gl is None or gl < 9 or gl > 12:
            continue
        is_current = (school_year == CURRENT_SCHOOL_YEAR)
        grid[gl]['is_historical'] = not is_current
        grid[gl]['is_current'] = is_current

        sorted_courses = sorted(courses.values(), key=lambda g: (g.is_semester or 1, g.period or 0))
        sem1 = [c for c in sorted_courses if (c.is_semester or 1) == 1]
        sem2 = [c for c in sorted_courses if (c.is_semester or 1) == 2]

        for i, g in enumerate(sem1[:SLOTS_PER_TERM]):
            grid[gl]['term1'][i] = {
                'slot': i, 'course_number': g.course_number or '',
                'course_title': g.course_name or '', 'credits': g.credits_earned or 5,
                'subject_area': g.subject_area or '', 'is_ag': g.is_ag or False,
                'letter_grade': g.letter_grade or '',
                'source': 'current' if is_current else 'historical',
            }
        for i, g in enumerate(sem2[:SLOTS_PER_TERM]):
            grid[gl]['term2'][i] = {
                'slot': i, 'course_number': g.course_number or '',
                'course_title': g.course_name or '', 'credits': g.credits_earned or 5,
                'subject_area': g.subject_area or '', 'is_ag': g.is_ag or False,
                'letter_grade': g.letter_grade or '',
                'source': 'current' if is_current else 'historical',
            }

    # Overlay planned courses from AcademicPlan
    plan = AcademicPlan.query.filter_by(student_id=student.id).first()
    if plan and plan.plan_json:
        try:
            plan_data = json.loads(plan.plan_json)
        except (json.JSONDecodeError, TypeError):
            plan_data = {}
        for gl_str, terms in plan_data.items():
            gl = int(gl_str)
            if gl < 9 or gl > 12:
                continue
            if grid[gl]['is_historical'] or grid[gl]['is_current']:
                continue
            grid[gl]['is_planned'] = True
            for term_key in ('term1', 'term2'):
                for slot_data in terms.get(term_key, []):
                    idx = slot_data.get('slot', 0)
                    if 0 <= idx < SLOTS_PER_TERM:
                        grid[gl][term_key][idx] = slot_data

    return grid


def _project_credits(student, grid):
    """Project credits/A-G/risk from historical grades + planned courses."""
    earned = _compute_credits_from_grades(student.id) or {}
    ag_earned = _compute_ag_from_grades(student.id) or {}

    # Start with earned credits by subject
    projected = defaultdict(float)
    for subj, data in earned.items():
        if subj == 'TOTALS':
            continue
        projected[subj] = data.get('completed', 0)

    # Add planned courses
    for gl in range(9, 13):
        year = grid.get(gl, {})
        if year.get('is_historical') or year.get('is_current'):
            continue
        for term_key in ('term1', 'term2'):
            for slot in year.get(term_key, []):
                if slot.get('source') in ('planned', 'ai') and slot.get('course_title'):
                    credits = slot.get('credits', 5)
                    subj_area = slot.get('subject_area', 'Electives')
                    mapped = _SUBJECT_MAP.get(subj_area, ['Electives'])
                    remaining = credits
                    for m in mapped:
                        req = GRAD_REQUIREMENTS.get(m, 0)
                        room = max(0, req - projected.get(m, 0))
                        alloc = min(remaining, room) if room > 0 else 0
                        if alloc > 0:
                            projected[m] += alloc
                            remaining -= alloc
                    if remaining > 0:
                        projected['Electives'] = projected.get('Electives', 0) + remaining

    # Build result
    credits_result = {}
    total_proj = 0
    gaps = []
    for subj, req in GRAD_REQUIREMENTS.items():
        comp = min(projected.get(subj, 0), req)
        need = max(0, req - projected.get(subj, 0))
        credits_result[subj] = {'required': req, 'projected': projected.get(subj, 0), 'gap': need}
        total_proj += projected.get(subj, 0)
        if need > 0:
            gaps.append((subj, need))

    total_gap = max(0, TOTAL_REQUIRED - total_proj)
    risk = _risk_level(total_proj, TOTAL_REQUIRED, 12)

    # A-G projection
    ag_projected = {}
    ag_met_count = 0
    ag_gaps = []
    if ag_earned:
        for area, data in ag_earned.items():
            proj_credits = data.get('completed', 0)
            ag_projected[area] = {
                'label': data.get('label', area),
                'required': data.get('required', 0),
                'projected': proj_credits,
                'isMet': data.get('isMet', False),
            }
            if data.get('isMet'):
                ag_met_count += 1
            else:
                ag_gaps.append((data.get('label', area), data.get('needed', 0)))

    # Graduation statement
    if total_gap == 0 and not gaps:
        statement = f"On track to graduate with {int(total_proj)}/{TOTAL_REQUIRED} credits."
    elif total_gap > 0:
        statement = f"Projected {int(total_proj)}/{TOTAL_REQUIRED} credits — short by {int(total_gap)}."
    else:
        short_subjs = ', '.join(f"{s} ({int(n)})" for s, n in gaps[:3])
        statement = f"Total credits OK ({int(total_proj)}/{TOTAL_REQUIRED}) but gaps in: {short_subjs}."

    if ag_met_count == 7:
        statement += " A-G requirements fully met."
    elif ag_gaps:
        statement += f" A-G: {ag_met_count}/7 met."

    return {
        'credits': credits_result,
        'total_projected': total_proj,
        'total_required': TOTAL_REQUIRED,
        'total_gap': total_gap,
        'gaps': gaps,
        'risk': risk,
        'ag': ag_projected,
        'ag_met': ag_met_count,
        'ag_gaps': ag_gaps,
        'statement': statement,
    }


# ── Routes ──────────────────────────────────────────────────────

@academic_plan_bp.route('/')
@login_required
def index():
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id,
        status='active'
    ).order_by(Student.grade_level.desc(), Student.last_name).all()

    rows = []
    for s in students:
        plan = AcademicPlan.query.filter_by(student_id=s.id).first()
        if plan:
            status = 'locked' if plan.is_locked else 'draft'
            risk = plan.projected_risk or 'unknown'
            credits = plan.projected_total_credits or 0
            ag = plan.projected_ag_met or 0
        else:
            status = 'none'
            risk = 'unknown'
            credits = 0
            ag = 0
        rows.append({
            'student': s,
            'plan_status': status,
            'risk': risk,
            'credits': credits,
            'ag': ag,
        })

    return render_template('academic_plan/index.html', rows=rows)


@academic_plan_bp.route('/student/<int:student_id>')
@login_required
def student_detail(student_id):
    student = Student.query.get_or_404(student_id)
    if student.assigned_counselor_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    grid = _build_grid(student)
    projection = _project_credits(student, grid)
    plan = AcademicPlan.query.filter_by(student_id=student.id).first()

    courses = Course.query.filter_by(is_active=True).order_by(Course.title).all()
    catalog = [{'course_number': c.course_number, 'title': c.title,
                'credits': c.credits or 5, 'subject_area': c.subject_area or '',
                'is_ag': bool(c.ncaa_approved),
                'grade_levels': c.grade_levels or '9,10,11,12',
                'course_type': c.course_type or 'elective'} for c in courses]

    return render_template('academic_plan/detail.html',
                           student=student, grid=grid, projection=projection,
                           plan=plan, catalog=catalog,
                           current_grade=student.grade_level or 9)


@academic_plan_bp.route('/student/<int:student_id>/save', methods=['POST'])
@login_required
def save_plan(student_id):
    student = Student.query.get_or_404(student_id)
    if student.assigned_counselor_id != current_user.id:
        return jsonify({'ok': False, 'error': 'Access denied'}), 403

    data = request.get_json()
    plan_data = data.get('plan', {})
    notes = data.get('notes', '')

    plan = AcademicPlan.query.filter_by(student_id=student.id).first()
    if not plan:
        plan = AcademicPlan(student_id=student.id, counselor_id=current_user.id)
        db.session.add(plan)

    plan.plan_json = json.dumps(plan_data)
    plan.notes = notes
    plan.counselor_id = current_user.id
    plan.is_locked = False

    # Recompute projections
    grid = _build_grid(student)
    # Overlay the just-submitted plan data into the grid for projection
    for gl_str, terms in plan_data.items():
        gl = int(gl_str)
        if gl < 9 or gl > 12:
            continue
        if grid[gl]['is_historical'] or grid[gl]['is_current']:
            continue
        grid[gl]['is_planned'] = True
        for term_key in ('term1', 'term2'):
            for slot_data in terms.get(term_key, []):
                idx = slot_data.get('slot', 0)
                if 0 <= idx < SLOTS_PER_TERM:
                    grid[gl][term_key][idx] = slot_data

    proj = _project_credits(student, grid)
    plan.projected_total_credits = proj['total_projected']
    plan.projected_ag_met = proj['ag_met']
    plan.projected_risk = proj['risk']

    db.session.commit()
    log_action('update', 'academic_plan', student.id)

    return jsonify({'ok': True, 'projection': proj})


@academic_plan_bp.route('/student/<int:student_id>/auto-build', methods=['POST'])
@login_required
def auto_build(student_id):
    student = Student.query.get_or_404(student_id)
    if student.assigned_counselor_id != current_user.id:
        return jsonify({'ok': False, 'error': 'Access denied'}), 403

    current_grade = student.grade_level or 9
    grid = _build_grid(student)

    # Build plan for each future year sequentially
    used_numbers = set()
    # Collect course numbers already in historical/current
    for gl in range(9, 13):
        year = grid.get(gl, {})
        for term_key in ('term1', 'term2'):
            for slot in year.get(term_key, []):
                cn = slot.get('course_number', '')
                if cn:
                    used_numbers.add(cn)

    plan_data = {}

    for target_gl in range(current_grade + 1, 13):
        term1, term2, _, _ = build_recommended_schedule(
            student,
            target_grade_level=target_gl,
            exclude_course_numbers=used_numbers,
        )

        year_plan = {'term1': [], 'term2': []}
        for i, item in enumerate(term1[:SLOTS_PER_TERM]):
            _, reasons, c = item
            slot = {
                'slot': i, 'course_number': c.course_number or '',
                'course_title': c.title or '', 'credits': c.credits or 5,
                'subject_area': c.subject_area or '', 'is_ag': bool(c.ncaa_approved),
                'source': 'ai', 'reason': reasons[0] if reasons else '',
            }
            year_plan['term1'].append(slot)
            if c.course_number:
                used_numbers.add(c.course_number)
        # Fill remaining term1 slots
        while len(year_plan['term1']) < SLOTS_PER_TERM:
            year_plan['term1'].append(_empty_slot(len(year_plan['term1'])))

        for i, item in enumerate(term2[:SLOTS_PER_TERM]):
            _, reasons, c = item
            slot = {
                'slot': i, 'course_number': c.course_number or '',
                'course_title': c.title or '', 'credits': c.credits or 5,
                'subject_area': c.subject_area or '', 'is_ag': bool(c.ncaa_approved),
                'source': 'ai', 'reason': reasons[0] if reasons else '',
            }
            year_plan['term2'].append(slot)
            if c.course_number:
                used_numbers.add(c.course_number)
        while len(year_plan['term2']) < SLOTS_PER_TERM:
            year_plan['term2'].append(_empty_slot(len(year_plan['term2'])))

        plan_data[str(target_gl)] = year_plan

    log_action('ai_feedback', 'academic_plan', student.id)
    return jsonify({'ok': True, 'plan': plan_data})


@academic_plan_bp.route('/student/<int:student_id>/lock', methods=['POST'])
@login_required
def lock_plan(student_id):
    student = Student.query.get_or_404(student_id)
    if student.assigned_counselor_id != current_user.id:
        return jsonify({'ok': False, 'error': 'Access denied'}), 403

    plan = AcademicPlan.query.filter_by(student_id=student.id).first()
    if not plan:
        return jsonify({'ok': False, 'error': 'No plan to lock'}), 400

    plan.is_locked = not plan.is_locked
    if plan.is_locked:
        plan.locked_at = datetime.now(timezone.utc)
        plan.counselor_signed_at = datetime.now(timezone.utc)
    else:
        plan.locked_at = None
        plan.counselor_signed_at = None

    db.session.commit()
    log_action('update', 'academic_plan', student.id)
    return jsonify({'ok': True, 'is_locked': plan.is_locked})


@academic_plan_bp.route('/student/<int:student_id>/api/projection')
@login_required
def projection_api(student_id):
    student = Student.query.get_or_404(student_id)
    if student.assigned_counselor_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    grid = _build_grid(student)
    proj = _project_credits(student, grid)
    return jsonify(proj)


@academic_plan_bp.route('/student/<int:student_id>/print')
@login_required
def print_plan(student_id):
    from datetime import date as _date
    student = Student.query.get_or_404(student_id)
    if student.assigned_counselor_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403

    grid = _build_grid(student)
    projection = _project_credits(student, grid)
    plan = AcademicPlan.query.filter_by(student_id=student.id).first()

    return render_template('academic_plan/print.html',
                           student=student, grid=grid, projection=projection,
                           plan=plan, today=_date.today().strftime('%B %d, %Y'))
