"""Graduation Tracker — credit audit, a-g progress, and at-risk identification."""
import json
from collections import defaultdict
from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app.models.student import Student
from app.models.grade import GradeRecord
from app.utils.roles import owned_or_404

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

# Credits a student can earn in one full year at this school. JUHSD runs an
# accelerated block — 4 classes x 4 quarters x 5 credits = 80 — so a student on
# full pace reaches the 225-credit requirement partway through grade 11.
#
# This number is the difference between a credit flag that means something and
# one that never fires: the previous benchmarks assumed roughly 55/year, so a
# 9th grader who had FAILED HALF their courses (40 of a possible 80) still read
# as "on-track", and in grades 10-12 that same student never got worse than
# "warning". Override per school in Settings -> Graduation Requirements.
DEFAULT_CREDITS_PER_YEAR = 80


def get_grad_policy(user=None):
    """Return this school's {'required', 'per_year'} credit policy.

    Reads the school config so a district with different numbers isn't stuck
    with JUHSD's. Falls back to the module defaults outside a request context
    (scripts, tests, the scale bench) so nothing here needs a logged-in user.
    """
    required, per_year = TOTAL_REQUIRED, DEFAULT_CREDITS_PER_YEAR
    try:
        if user is None:
            from flask_login import current_user
            user = current_user if getattr(current_user, 'is_authenticated', False) else None
        if user is not None:
            from app.utils.school_config import get_school_config
            cfg = get_school_config(user)
            required = _positive(cfg.get('credits_required'), required)
            per_year = _positive(cfg.get('credits_per_year'), per_year)
    except Exception:
        pass                      # never let a config read break a grad view
    return {'required': required, 'per_year': per_year}


def _positive(value, fallback):
    try:
        n = float(value)
        return n if n > 0 else fallback
    except (TypeError, ValueError):
        return fallback

# California State Minimum (Ed Code 51225.3) — for AB exemption-eligible students
# 13 year-long courses = 130 credits. No electives required at state level.
STATE_MIN_REQUIREMENTS = {
    'English': 30, 'Math': 20,
    'Life Science': 10, 'Physical Science': 10,
    'US History': 10, 'World History, CLT': 10, 'Economics': 5, 'Government': 5,
    'Fine Arts / LOTE': 10, 'Physical Education': 20,
}
STATE_MIN_TOTAL = 130

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
    # Math overflow fills the 10-credit State Math Requirement bucket — matches
    # the transcript front-end (gradSubjects: ['Math', 'State Math Requirement']).
    # Without this, nothing ever maps to State Math, so even a student who passed
    # all 225 credits caps at 215 and shows 10 credits short of graduation.
    'Math':                    ['Math', 'State Math Requirement'],
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
    # NOTE: `not g.is_passing` is CORRECT here, unlike in mail_merge/meeting_prep.
    # is_passing is None for ungraded 'NM', and an ungraded course must not count
    # toward earned credit — so folding None in with False is the intended
    # outcome. Do not "fix" this to `is False` in a mechanical sweep.
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
    # NOTE: `not g.is_passing` is CORRECT here, unlike in mail_merge/meeting_prep.
    # is_passing is None for ungraded 'NM', and an ungraded course must not count
    # toward earned credit — so folding None in with False is the intended
    # outcome. Do not "fix" this to `is False` in a mechanical sweep.
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


def expected_credits_by_end_of(grade_level, total_required=None, per_year=None):
    """Credits a student should hold at the END of ``grade_level``.

    Earning capacity x years completed, CAPPED at the graduation requirement —
    never expect more than it takes to graduate. At JUHSD's 80/year that gives
    80 / 160 / 225 / 225 for grades 9-12, rather than the old 34 / 90 / 146 /
    191, whose top end was the giveaway: it expected only 85% of the credits
    needed to graduate at the end of senior year, so a student could hit every
    benchmark and still not graduate.
    """
    if not grade_level or grade_level < 9 or grade_level > 12:
        return None
    policy = get_grad_policy()
    required = total_required or policy['required']
    per_year = per_year or policy['per_year']
    return min(per_year * (grade_level - 8), required)


def _risk_level(total_completed, total_required, grade_level, per_year=None):
    """Graduation risk from credits earned, against this school's real pace.

    Two independent signals, worst one wins:

    1. PACE — earned vs. what a student on full pace would hold by now.
    2. FEASIBILITY — whether the requirement is still mathematically reachable:
       earned + (per_year x years remaining) >= required. A junior 100 credits
       in with one year and 80 credits of capacity left CANNOT finish on time,
       and no pace ratio expresses that. This check can only make the verdict
       worse, never better.
    """
    if not grade_level or not total_required:
        return 'unknown'
    policy = get_grad_policy()
    per_year = per_year or policy['per_year']
    total_completed = total_completed or 0

    expected = expected_credits_by_end_of(grade_level, total_required, per_year)
    if not expected:
        return 'unknown'

    if total_completed < expected * 0.6:
        level = 'critical'
    elif total_completed < expected * 0.8:
        level = 'at-risk'
    elif total_completed < expected * 0.95:
        level = 'warning'
    else:
        level = 'on-track'

    years_left = max(0, 12 - grade_level)
    if total_completed + per_year * years_left < total_required:
        level = 'critical'          # cannot reach the requirement in time
    return level


def can_still_graduate_on_time(total_completed, grade_level,
                               total_required=None, per_year=None):
    """Whether the requirement is still reachable by the end of grade 12.

    Exposed separately so the action plan can say "needs a credit-recovery
    plan beyond a normal schedule" instead of only colouring a badge.
    """
    if not grade_level or grade_level > 12:
        return True
    policy = get_grad_policy()
    required = total_required or policy['required']
    per_year = per_year or policy['per_year']
    years_left = max(0, 12 - grade_level)
    return (total_completed or 0) + per_year * years_left >= required

EXPECTED_AG_BY_GRADE = {
    9:  (0, 1, "foundation building"),
    10: (1, 2, "typical mid-career"),
    11: (3, 5, "approaching college-ready"),
    12: (5, 7, "should be near complete"),
}


def expected_progress(grade_level, quarter=4, total_required=None, per_year=None):
    """Return grade- AND quarter-relative expectations.

    Quarter is 1-4; defaults to 4 (year-end). Interpolates linearly between
    the end of the previous grade and the end of this one, both derived from
    the school's actual earning capacity rather than hardcoded percentages.
    Returns None outside grades 9-12 (middle school has no HS baseline).
    """
    if not grade_level or grade_level < 9 or grade_level > 12:
        return None
    policy = get_grad_policy()
    required = total_required or policy['required']
    per_year = per_year or policy['per_year']

    quarter = max(1, min(int(quarter or 4), 4))
    start = expected_credits_by_end_of(grade_level - 1, required, per_year) or 0
    end = expected_credits_by_end_of(grade_level, required, per_year)
    credits_expected = start + (end - start) * (quarter / 4)

    ag_low, ag_high, ag_label = EXPECTED_AG_BY_GRADE[grade_level]
    return {
        'credits_expected': round(credits_expected),
        'credits_pct': (credits_expected / required) if required else 0,
        'quarter': quarter,
        'ag_expected_low': ag_low,
        'ag_expected_high': ag_high,
        'ag_label': ag_label,
    }


def projected_credits(total_completed, total_wip):
    """Optimistic projection assuming all WIP courses pass."""
    return (total_completed or 0) + (total_wip or 0)


def pace_label(total_completed, total_wip, grade_level, quarter=4):
    """Translate (completed + WIP) into LLM-friendly prose.

    Compares the PROJECTED total against the quarter-appropriate
    expectation. Matches the counselor's working assumption that WIP
    courses will pass unless proven otherwise.

    Returns 'pace unknown' for the all-zero case (completed=0 AND wip=0):
    that typically means transcript data hasn't been imported yet for the
    current term, not that the student has actually failed everything.
    """
    exp = expected_progress(grade_level, quarter=quarter)
    if not exp or not exp['credits_expected']:
        return 'pace unknown'
    projected = projected_credits(total_completed, total_wip)
    if projected == 0:
        return 'pace unknown'
    ratio = projected / exp['credits_expected']
    if ratio >= 1.05:
        return 'ahead of pace'
    if ratio >= 0.95:
        return 'on pace'
    if ratio >= 0.80:
        return 'slightly behind pace'
    if ratio >= 0.60:
        return 'behind pace'
    return 'critically behind pace'


def _subject_deficiency(credits_data):
    """Calculate total subject-level deficiency from credits breakdown.

    Even if total credits exceed 225, individual subjects may be short.
    Returns (total_shortfall, num_subjects_short).
    """
    if not credits_data:
        return 0, 0
    shortfall = 0
    num_short = 0
    for subj, data in credits_data.items():
        if subj == 'TOTALS':
            continue
        req = data.get('required', 0) or 0
        comp = data.get('completed', 0) or 0
        if comp < req:
            shortfall += req - comp
            num_short += 1
    return shortfall, num_short


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
            risk = _risk_level(total_comp, TOTAL_REQUIRED, student.grade_level)
        else:
            total_comp = 0
            risk = 'unknown'

        if ag:
            ag_met = sum(1 for v in ag.values() if v.get('isMet'))
            ag_status = 'on-track' if ag_met == 7 else ('deficient' if ag_met < 5 else 'verify')
        else:
            ag_met = 0
            ag_status = 'unknown'

        source = 'grades' if credits else 'none'

    # Subject-level deficiency: the REAL credits needed even if total > 225
    subj_shortfall, subj_short_count = _subject_deficiency(credits)
    # "Credits needed" is the higher of total shortfall or subject shortfall
    total_need_raw = max(0, TOTAL_REQUIRED - total_comp)
    total_need = max(total_need_raw, subj_shortfall)

    # Progress percentage: use subject completion ratio, not just total credits
    # A student with 275/225 total but missing 10 credits in subjects is NOT 100%
    if credits and TOTAL_REQUIRED:
        # Sum credits earned per subject, capped at each subject's requirement
        subj_satisfied = 0
        for subj, data in credits.items():
            if subj == 'TOTALS':
                continue
            req = data.get('required', 0) or 0
            comp = data.get('completed', 0) or 0
            subj_satisfied += min(comp, req)
        pct = round(subj_satisfied / TOTAL_REQUIRED * 100)
    else:
        pct = round(total_comp / TOTAL_REQUIRED * 100) if TOTAL_REQUIRED else 0

    result = {
        'student': student,
        'total_completed': total_comp,
        'total_needed': total_need,
        'total_required': TOTAL_REQUIRED,
        'pct': pct,
        'subj_shortfall': subj_shortfall,
        'subj_short_count': subj_short_count,
        'risk': risk,
        'ag_met': ag_met,
        'ag_status': ag_status,
        'credits': credits,
        'ag': ag,
        'source': source,
    }

    # Dual-track: compute state minimum progress for AB-eligible students
    if student.has_ab_population and credits:
        sm_shortfall = 0
        sm_short_count = 0
        sm_satisfied = 0
        for subj, req in STATE_MIN_REQUIREMENTS.items():
            c = credits.get(subj, {})
            comp = c.get('completed', 0) or 0
            capped = min(comp, req)
            sm_satisfied += capped
            gap = max(0, req - comp)
            if gap > 0:
                sm_shortfall += gap
                sm_short_count += 1
        sm_total_need = max(max(0, STATE_MIN_TOTAL - total_comp), sm_shortfall)
        sm_pct = round(sm_satisfied / STATE_MIN_TOTAL * 100) if STATE_MIN_TOTAL else 0
        sm_risk = _risk_level(total_comp, STATE_MIN_TOTAL, student.grade_level)
        result['state_min'] = {
            'total_required': STATE_MIN_TOTAL,
            'total_needed': sm_total_need,
            'pct': sm_pct,
            'subj_shortfall': sm_shortfall,
            'subj_short_count': sm_short_count,
            'risk': sm_risk,
        }
    else:
        result['state_min'] = None

    return result


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

    # Exemption summary
    exemption_count = sum(1 for r in rows if r.get('state_min'))

    return render_template('graduation/index.html',
                           rows=rows,
                           risk_counts=risk_counts,
                           total_required=TOTAL_REQUIRED,
                           grad_requirements=GRAD_REQUIREMENTS,
                           ag_requirements=AG_REQUIREMENTS,
                           state_min_total=STATE_MIN_TOTAL,
                           exemption_count=exemption_count)


@graduation_bp.route('/student/<int:student_id>')
@login_required
def student_detail(student_id):
    """Detailed credit audit for a single student."""
    # Caseload-scoped: never render another counselor's (or a shadow student's)
    # name, transcript, and credit audit from a guessed URL id.
    student = owned_or_404(Student, student_id, owner_attr='assigned_counselor_id')
    data = _build_student_grad_data(student)

    # Get grade records for the detailed view
    grades = GradeRecord.query.filter_by(student_id=student_id).order_by(
        GradeRecord.school_year.desc(), GradeRecord.quarter.desc()
    ).all()

    return render_template('graduation/detail.html',
                           data=data, grades=grades,
                           grad_requirements=GRAD_REQUIREMENTS,
                           ag_requirements=AG_REQUIREMENTS,
                           total_required=TOTAL_REQUIRED,
                           state_min_requirements=STATE_MIN_REQUIREMENTS,
                           state_min_total=STATE_MIN_TOTAL)
