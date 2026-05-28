"""End-of-year rollover: per-student action defaults and anomaly detection."""
from app.models.student import Student, Tag


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
    """Return {risk, total_needed} for the rollover flag, or None.

    Prefers the cached risk_level on the most recent TranscriptRecord; falls
    back to live computation against grade records only when no transcript
    exists. Returns None when risk cannot be determined.
    """
    latest = student.transcript_records.first()
    if latest and latest.risk_level and latest.risk_level != 'unknown':
        return {
            'risk': latest.risk_level,
            'total_needed': latest.total_needed or 0,
        }
    try:
        from app.routes.graduation import _build_student_grad_data
        data = _build_student_grad_data(student)
    except Exception:
        return None
    risk = data.get('risk') if data else None
    if not risk or risk == 'unknown':
        return None
    return {'risk': risk, 'total_needed': data.get('total_needed', 0)}


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
        if cs and cs.get('risk') in ('critical', 'at-risk'):
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
    if cs and cs.get('risk') in ('critical', 'at-risk'):
        needed = cs.get('total_needed', 0)
        if needed > 0:
            flags.append(f"credits {cs['risk']}: {int(needed)} short")
        else:
            flags.append(f"credits {cs['risk']}")
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
        'had_senior_studies_tag': _has_senior_studies_tag(student),
    }


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
