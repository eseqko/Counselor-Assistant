"""End-of-year rollover: per-student action defaults and anomaly detection."""
from app.models.student import Tag


# Allowed per-row actions. Keep in sync with the dropdown in rollover.html and
# the apply_action() switch below.
ACTIONS = [
    ('promote', 'Promote (next grade)'),
    ('graduate', 'Graduate'),
    ('senior_studies', 'Senior Studies / 5th Year (continue at grade 12)'),
    ('retain', 'Retain (no change)'),
    ('transfer', 'Transferred out'),
    ('dropout', 'Dropped out'),
    ('skip', 'Skip (no change)'),
]
ACTION_KEYS = {k for k, _ in ACTIONS}


SENIOR_STUDIES_TAG = 'Senior Studies'


def protected_5th_year_reasons(student):
    """Return ED-Code-cited reasons the student may be entitled to a 5th year.

    Used to (a) suppress the auto-graduate default for 12th graders with any
    of these statuses, and (b) surface the citation in the anomaly banner so
    the counselor sees WHY the row needs review.
    """
    reasons = []
    if student.iep_status:
        reasons.append('IEP (IDEA transition, age 22)')
    if student.el_status == 'Newcomer':
        reasons.append('Newcomer EL (AB 2121)')
    if student.is_foster_youth:
        reasons.append('Foster Youth (AB 167/216)')
    if student.is_homeless:
        reasons.append('Homeless (AB 1806)')
    if student.is_migrant_newcomer:
        reasons.append('Migrant/Newcomer (AB 2121)')
    if student.is_formerly_incarcerated:
        reasons.append('Formerly Incarcerated (AB 2306/1124)')
    if student.is_military_connected:
        reasons.append('Military Connected (AB 365)')
    return reasons


def credit_status_summary(student):
    """Return WIP-aware credit summary for the rollover flag, or None.

    Uses the transcript's actual (completed, WIP, quarter) tuple. Two
    different gap measures, used for different decisions:

    * `behind_pace` — projected vs the quarter-appropriate expectation.
      Used for grades 9-11 (the question is whether they're on grade-pace).
    * `short_of_graduation` — projected vs the 225-credit graduation
      requirement. Used for grade 12 (the question is whether they will
      actually graduate this spring).

    Returns None when no usable data exists.
    """
    from app.routes.graduation import (expected_progress, projected_credits,
                                       pace_label, TOTAL_REQUIRED)
    from app.utils.helpers import parse_transcript_quarter, current_quarter

    latest = student.transcript_records.first()
    if not latest:
        return None

    completed = int(latest.total_completed or 0)
    wip = int(latest.total_wip or 0)
    if completed == 0 and wip == 0:
        return None

    quarter = current_quarter()
    if latest.quarter:
        _, q_from_tr = parse_transcript_quarter(latest.quarter)
        if q_from_tr:
            quarter = q_from_tr

    exp = expected_progress(student.grade_level, quarter=quarter)
    if not exp:
        return None

    projected = projected_credits(completed, wip)
    pace = pace_label(completed, wip, student.grade_level, quarter=quarter)
    return {
        'pace': pace,
        'completed': completed,
        'wip': wip,
        'projected': projected,
        'expected': exp['credits_expected'],
        'behind_pace': max(0, exp['credits_expected'] - projected),
        'short_of_graduation': max(0, TOTAL_REQUIRED - projected),
    }


_BEHIND_PACE_LABELS = ('behind pace', 'critically behind pace')
# Senior is "skipped" from auto-graduate if projected total is more than
# this many credits short of the 225 graduation requirement. Small slack so
# late-posting grades don't trigger needless review.
_SENIOR_GRADUATION_SLACK = 5


def default_action(student, credit_status=None):
    """Pick the default action for a student in the review page.

    `credit_status` is an optional pre-computed summary from
    credit_status_summary(). Routes that render many students should pass it
    in to avoid double-computing.
    """
    if student.grade_level is None:
        return 'skip'
    if student.grade_level > 12 or student.grade_level < 6:
        return 'skip'
    if _has_senior_studies_tag(student):
        return 'graduate'
    if student.grade_level == 12:
        if protected_5th_year_reasons(student):
            return 'skip'
        cs = credit_status_summary(student) if credit_status is None else credit_status
        # For seniors, the decisive question is "will projected total reach
        # the graduation requirement?" — not quarter-pace. A senior at
        # 155 projected vs 191 expected is "slightly behind pace" but still
        # 70 credits short of graduating. Skip unless within 5 credits of 225.
        if cs and cs.get('short_of_graduation', 0) > _SENIOR_GRADUATION_SLACK:
            return 'skip'
        return 'graduate'
    return 'promote'


def detect_anomalies(student, credit_status=None):
    """Return a list of short anomaly labels for the student, or []."""
    flags = []
    if student.grade_level is None:
        flags.append('no grade level')
    elif student.grade_level > 12:
        flags.append(f'grade {student.grade_level} (>12)')
    elif student.grade_level < 6:
        flags.append(f'grade {student.grade_level} (<6)')
    if student.exit_date:
        flags.append('exit_date already set')
    if student.status != 'active':
        flags.append(f'status={student.status}')
    if _has_senior_studies_tag(student):
        flags.append('already in Senior Studies')
    if student.grade_level == 12:
        reasons = protected_5th_year_reasons(student)
        if reasons:
            flags.append('eligible for 5th year: ' + ', '.join(reasons))

    cs = credit_status_summary(student) if credit_status is None else credit_status
    if cs:
        completed = cs.get('completed', 0)
        wip = cs.get('wip', 0)
        projected = cs.get('projected', 0)

        # Senior-specific: surface graduation shortfall when projected won't
        # reach 225, regardless of "pace" label.
        if (student.grade_level == 12
                and cs.get('short_of_graduation', 0) > _SENIOR_GRADUATION_SLACK):
            short = int(cs['short_of_graduation'])
            wip_phrase = f"{completed}+{wip} WIP" if wip else f"{completed}"
            flags.append(
                f"projected short of graduation: {wip_phrase} = {projected}/225 ({short} short)"
            )
        # Lower-grade flag: pace-behind (so counselor can plan interventions
        # for next year). Skip when senior-shortfall flag already covered it.
        elif cs.get('pace') in _BEHIND_PACE_LABELS:
            expected = cs.get('expected', 0)
            behind = int(cs.get('behind_pace', 0))
            wip_phrase = f"({wip} WIP, {behind} short after WIP)" if wip else f"(0 WIP, {behind} short)"
            flags.append(f"credits {cs['pace']}: {completed}/{expected} {wip_phrase}")
    return flags


def apply_action(student, action, end_date):
    """Mutate `student` according to `action`. Returns a snapshot dict of the
    student's prior state so it can be restored later.

    `end_date` is the school-year-end Date — used for exit_date.
    """
    prior = _capture_prior(student)

    if action == 'promote':
        if student.grade_level is not None:
            student.grade_level = student.grade_level + 1
    elif action == 'graduate':
        student.status = 'graduated'
        student.exit_reason = 'graduated'
        student.exit_date = end_date
    elif action == 'senior_studies':
        # Stay at grade 12, active; tag them. Do not promote past 12.
        if student.grade_level is not None and student.grade_level < 12:
            student.grade_level = 12
        student.status = 'active'
        _ensure_tag(student, SENIOR_STUDIES_TAG)
    elif action == 'retain':
        pass  # explicit no-op
    elif action == 'transfer':
        student.status = 'transferred'
        student.exit_reason = 'transferred_out_district'
        student.exit_date = end_date
    elif action == 'dropout':
        student.status = 'inactive'
        student.exit_reason = 'dropped_out'
        student.exit_date = end_date
    # 'skip' -> no-op

    return prior


def restore(student, prior):
    """Restore a student to a previously captured prior state."""
    student.grade_level = prior.get('grade_level')
    student.status = prior.get('status') or 'active'
    student.exit_reason = prior.get('exit_reason')
    student.exit_date = _parse_iso_date(prior.get('exit_date'))
    student.exit_notes = prior.get('exit_notes')
    # Caseload-sync snapshots also capture the counselor assignment (the
    # 'unassign' action clears it). Old rollover snapshots predate the key —
    # leave the assignment untouched for those.
    if 'assigned_counselor_id' in prior:
        student.assigned_counselor_id = prior['assigned_counselor_id']

    # Restore Senior Studies tag membership only — leave other tags alone, since
    # rollover only ever adds the SENIOR_STUDIES_TAG, never removes anything.
    had_tag = prior.get('had_senior_studies_tag', False)
    if not had_tag and _has_senior_studies_tag(student):
        ss = next((t for t in student.tags if t.name == SENIOR_STUDIES_TAG), None)
        if ss:
            student.tags.remove(ss)


def _capture_prior(student):
    return {
        'student_id': student.id,
        'grade_level': student.grade_level,
        'status': student.status,
        'exit_reason': student.exit_reason,
        'exit_date': student.exit_date.isoformat() if student.exit_date else None,
        'exit_notes': student.exit_notes,
        'assigned_counselor_id': student.assigned_counselor_id,
        'had_senior_studies_tag': _has_senior_studies_tag(student),
    }


# ── New-year caseload sync ("departing student" actions) ─────────────────────
# Applied to students on the counselor's caseload who are ABSENT from a newly
# uploaded roster file. 'keep' is the safe default and a strict no-op.
SYNC_ACTIONS = ('keep', 'transfer', 'graduate', 'withdraw', 'unassign')


def apply_sync_action(student, action, end_date):
    """Apply a caseload-sync departing action; returns the captured prior state.

    Mirrors apply_action's contract (capture first, then mutate) so the same
    RolloverSnapshot/restore machinery provides the 24-hour undo.
    """
    prior = _capture_prior(student)

    if action == 'transfer':
        student.status = 'transferred'
        student.exit_reason = 'transferred_out_district'
        student.exit_date = end_date
    elif action == 'graduate':
        student.status = 'graduated'
        student.exit_reason = 'graduated'
        student.exit_date = end_date
    elif action == 'withdraw':
        student.status = 'inactive'
        student.exit_reason = 'other'
        student.exit_date = end_date
    elif action == 'unassign':
        # Moving to another counselor: stays active in the school, drops off
        # this caseload, appears in the admin unassigned pool for pickup.
        # Deliberately NOT an exit — no exit_reason/date on an active student.
        student.assigned_counselor_id = None
    # 'keep' -> no-op

    return prior


def _parse_iso_date(s):
    if not s:
        return None
    from datetime import date
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def _has_senior_studies_tag(student):
    return any(t.name == SENIOR_STUDIES_TAG for t in student.tags)


def _ensure_tag(student, name):
    from app import db
    if _has_senior_studies_tag(student):
        return
    tag = Tag.query.filter_by(name=name).first()
    if not tag:
        tag = Tag(name=name, color='#8B5CF6')
        db.session.add(tag)
        db.session.flush()
    student.tags.append(tag)
