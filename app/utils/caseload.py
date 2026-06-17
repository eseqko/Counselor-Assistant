"""Caseload-scoped query helpers.

These wrap the common 'give me my caseload's student IDs' pattern so we
don't repeat the filter_by + with_entities + comprehension in every route.
"""
from app.models.student import Student


def caseload_student_ids(user, status=None):
    """Return a list of student database IDs assigned to user.

    Optionally filter by Student.status (e.g. 'active'). Excludes the per-user
    "Sample Student" (screener test vehicle) so it never enters analytics.
    """
    q = Student.query.filter_by(assigned_counselor_id=user.id).filter(
        Student.is_sample == False)
    if status is not None:
        q = q.filter_by(status=status)
    return [row[0] for row in q.with_entities(Student.id).all()]


def get_or_create_sample_student(user):
    """Return this counselor's "Sample Student", creating it if needed.

    A lightweight, clearly-labeled placeholder for trying out screeners (and
    other tools) without touching a real student. Assigned to the counselor so
    it passes ownership checks and appears in tool dropdowns, but flagged
    is_sample=True so caseload rosters, counts, and analytics skip it.
    """
    from app import db
    sample = Student.query.filter_by(
        assigned_counselor_id=user.id, is_sample=True).first()
    if sample:
        return sample
    sample = Student(
        first_name='Sample',
        last_name='Student',
        student_id_number=f'SAMPLE-{user.id}',
        assigned_counselor_id=user.id,
        status='active',
        is_sample=True,
    )
    db.session.add(sample)
    db.session.commit()
    return sample

