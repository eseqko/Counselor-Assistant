"""Caseload-scoped query helpers.

These wrap the common 'give me my caseload's student IDs' pattern so we
don't repeat the filter_by + with_entities + comprehension in every route.
"""
from app.models.student import Student


def caseload_student_ids(user, status=None):
    """Return a list of student database IDs assigned to user.

    Optionally filter by Student.status (e.g. 'active').
    """
    q = Student.query.filter_by(assigned_counselor_id=user.id)
    if status is not None:
        q = q.filter_by(status=status)
    return [row[0] for row in q.with_entities(Student.id).all()]
