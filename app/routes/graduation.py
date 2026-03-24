"""Graduation Tracker — credit audit, a-g progress, and at-risk identification."""
import json
from collections import defaultdict
from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app import db
from app.models.student import Student
from app.models.grade import GradeRecord
from app.models.transcript import TranscriptRecord

graduation_bp = Blueprint('graduation', __name__)

# ── Graduation requirements (matching transcript_batch.html) ──────
GRAD_REQUIREMENTS = {
    'English': 40, 'Math': 20, 'State Math Requirement': 10,
    'Life Science': 10, 'Physical Science': 10, 'Economics': 5,
    'Government': 5, 'US History': 10, 'World History, CLT': 10,
    'Fine Arts / LOTE': 10, 'Career Technical Education': 10,
    'Physical Education': 20, 'Health Education': 5, 'Electives': 60,
}
TOTAL_REQUIRED = 225

AG_REQUIREMENTS = {
    'a': {'label': 'History/Social Science', 'required': 20},
    'b': {'label': 'English', 'required': 40},
    'c': {'label': 'Mathematics', 'required': 30},
    'd': {'label': 'Lab Science', 'required': 20},
    'e': {'label': 'LOTE', 'required': 20},
    'f': {'label': 'VPA', 'required': 10},
    'g': {'label': 'College-Prep Elective', 'required': 10},
}

# Map GradeRecord subject_area to grad requirement subjects
_SUBJECT_MAP = {
    'English':                 ['English'],
    'Math':                    ['Math'],
    'Science':                 ['Life Science', 'Physical Science'],
    'History/Social Science':  ['US History', 'World History, CLT', 'Government', 'Economics'],
    'Fine Arts/LOTE':          ['Fine Arts / LOTE'],
    'CTE':                     ['Career Technical Education'],
    'PE':                      ['Physical Education'],
    'Health':                  ['Health Education'],
    'Electives':               ['Electives'],
}

# Map subject_area → a-g areas
_SUBJECT_TO_AG = {
    'English':                'b',
    'Math':                   'c',
    'Science':                'd',
    'History/Social Science': 'a',
    'Fine Arts/LOTE':         'f',  # Could be e or f — simplified
    'Electives':              'g',
}


def _compute_credits_from_grades(student_id):
    """Compute credit summary from GradeRecords for a student.

    Returns dict like {subject: {required, completed, needed}} plus 'TOTALS'.
    """
    grades = GradeRecord.query.filter_by(student_id=student_id).all()
    if not grades:
        return None

    # Accumulate passing credits by mapped grad-requirement subjects
    earned = defaultdict(float)
    for g in grades:
        if not g.is_passing:
            continue
        credits = g.credits_earned or 5.0
        subj = g.subject_area or 'Electives'
        mapped = _SUBJECT_MAP.get(subj, ['Electives'])
        # Distribute credits to the first mapped subject that still needs them
        remaining = credits
        for m in mapped:
            req = GRAD_REQUIREMENTS.get(m, 0)
            room = max(0, req - earned[m])
            alloc = min(remaining, room) if room > 0 else 0
            if alloc > 0:
                earned[m] += alloc
                remaining -= alloc
        # Any remainder goes to Electives
        if remaining > 0:
            earned['Electives'] += remaining

    result = {}
    total_req = 0
    total_comp = 0
    for subj, req in GRAD_REQUIREMENTS.items():
        comp = min(earned.get(subj, 0), req)
        need = max(0, req - comp)
        result[subj] = {'required': req, 'completed': comp, 'wip': 0, 'need': need}
        total_req += req
        total_comp += comp

    result['TOTALS'] = {
        'required': TOTAL_REQUIRED,
        'completed': total_comp,
        'wip': 0,
        'need': max(0, TOTAL_REQUIRED - total_comp),
    }
    return result


def _compute_ag_from_grades(student_id):
    """Compute a-g progress from GradeRecords."""
    grades = GradeRecord.query.filter_by(student_id=student_id).all()
    if not grades:
        return None

    earned = defaultdict(float)
    for g in grades:
        if not g.is_passing or not g.is_ag:
            continue
        credits = g.credits_earned or 5.0
        subj = g.subject_area or ''
        ag_area = _SUBJECT_TO_AG.get(subj)
        if ag_area:
            earned[ag_area] += credits

    result = {}
    for area, info in AG_REQUIREMENTS.items():
        comp = min(earned.get(area, 0), info['required'])
        result[area] = {
            'label': info['label'],
            'required': info['required'],
            'completed': comp,
            'needed': max(0, info['required'] - comp),
            'isMet': comp >= info['required'],
        }
    return result


def _risk_level(total_completed, total_required, grade_level):
    """Compute graduation risk level based on credits and grade."""
    if not grade_level or not total_required:
        return 'unknown'
    # Expected progress: roughly proportional to semesters completed
    # Grade 9 end ≈ 25%, Grade 10 end ≈ 50%, Grade 11 end ≈ 75%, Grade 12 end = 100%
    expected_pct = {9: 0.15, 10: 0.40, 11: 0.65, 12: 0.85}
    expected = total_required * expected_pct.get(grade_level, 0.5)
    pct = total_completed / total_required if total_required else 0

    if total_completed < expected * 0.6:
        return 'critical'
    elif total_completed < expected * 0.8:
        return 'at-risk'
    elif total_completed < expected * 0.95:
        return 'warning'
    return 'on-track'


def _build_student_grad_data(student):
    """Build graduation data for a single student, preferring transcript if available."""
    latest = student.transcript_records.first()

    if latest and latest.credits_json:
        # Use imported transcript data
        try:
            credits = json.loads(latest.credits_json)
        except (json.JSONDecodeError, TypeError):
            credits = None
        try:
            ag = json.loads(latest.ag_json) if latest.ag_json else None
        except (json.JSONDecodeError, TypeError):
            ag = None

        totals = credits.get('TOTALS', {}) if credits else {}
        total_comp = totals.get('completed', latest.total_completed or 0)
        total_need = totals.get('need', latest.total_needed or 0)
        risk = latest.risk_level or 'unknown'
        ag_met = latest.ag_areas_met or 0
        ag_status = latest.ag_status or 'unknown'
        source = 'transcript'
    else:
        # Compute from grade records
        credits = _compute_credits_from_grades(student.id)
        ag = _compute_ag_from_grades(student.id)

        if credits:
            totals = credits.get('TOTALS', {})
            total_comp = totals.get('completed', 0)
            total_need = totals.get('need', 0)
            risk = _risk_level(total_comp, TOTAL_REQUIRED, student.grade_level)
        else:
            total_comp = 0
            total_need = TOTAL_REQUIRED
            risk = 'unknown'

        if ag:
            ag_met = sum(1 for v in ag.values() if v.get('isMet'))
            ag_status = 'on-track' if ag_met == 7 else ('deficient' if ag_met < 5 else 'verify')
        else:
            ag_met = 0
            ag_status = 'unknown'

        source = 'grades' if credits else 'none'

    return {
        'student': student,
        'total_completed': total_comp,
        'total_needed': total_need,
        'total_required': TOTAL_REQUIRED,
        'pct': round(total_comp / TOTAL_REQUIRED * 100) if TOTAL_REQUIRED else 0,
        'risk': risk,
        'ag_met': ag_met,
        'ag_status': ag_status,
        'credits': credits,
        'ag': ag,
        'source': source,
    }


@graduation_bp.route('/')
@login_required
def index():
    """Caseload-wide graduation tracker."""
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id,
        status='active'
    ).order_by(Student.grade_level.desc(), Student.last_name).all()

    rows = [_build_student_grad_data(s) for s in students]

    # Summary counts
    risk_counts = defaultdict(int)
    for r in rows:
        risk_counts[r['risk']] += 1

    return render_template('graduation/index.html',
                           rows=rows,
                           risk_counts=risk_counts,
                           total_required=TOTAL_REQUIRED,
                           grad_requirements=GRAD_REQUIREMENTS,
                           ag_requirements=AG_REQUIREMENTS)


@graduation_bp.route('/student/<int:student_id>')
@login_required
def student_detail(student_id):
    """Detailed credit audit for a single student."""
    student = Student.query.get_or_404(student_id)
    data = _build_student_grad_data(student)

    # Get grade records for the detailed view
    grades = GradeRecord.query.filter_by(student_id=student_id).order_by(
        GradeRecord.school_year.desc(), GradeRecord.quarter.desc()
    ).all()

    return render_template('graduation/detail.html',
                           data=data, grades=grades,
                           grad_requirements=GRAD_REQUIREMENTS,
                           ag_requirements=AG_REQUIREMENTS,
                           total_required=TOTAL_REQUIRED)
