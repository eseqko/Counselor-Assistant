"""End-of-year rollover: per-student action defaults and anomaly detection."""
from app.models.student import Student, Tag


# Allowed per-row actions. Keep in sync with the dropdown in rollover.html and
# the apply_action() switch below.
ACTIONS = [
    ('promote', 'Promote (next grade)'),
    ('graduate', 'Graduate'),
    ('senior_studies', 'Senior Studies (continue at grade 12)'),
    ('retain', 'Retain (no change)'),
    ('transfer', 'Transferred out'),
    ('dropout', 'Dropped out'),
    ('skip', 'Skip (no change)'),
]
ACTION_KEYS = {k for k, _ in ACTIONS}


SENIOR_STUDIES_TAG = 'Senior Studies'


def default_action(student):
    """Pick the default action for a student in the review page."""
    if student.grade_level is None:
        return 'skip'
    if student.grade_level > 12 or student.grade_level < 6:
        return 'skip'
    if _has_senior_studies_tag(student):
        return 'graduate'
    if student.grade_level == 12:
        return 'graduate'
    return 'promote'


def detect_anomalies(student):
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
