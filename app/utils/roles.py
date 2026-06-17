"""Role-based access control utilities."""
from functools import wraps
from flask import flash, redirect, url_for, abort
from flask_login import current_user


def admin_required(f):
    """Decorator: user must be logged in and have role='admin'."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if current_user.role != 'admin':
            flash('Admin access required.', 'error')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated


def owned_or_404(model, obj_id, owner_attr='counselor_id'):
    """Fetch a record by id, scoped to the current user's ownership.

    Admins bypass the ownership check (department-wide oversight). For everyone
    else, a record owned by another counselor returns 404 — NOT 403 — so the
    endpoint never confirms the existence of another counselor's student data
    (prevents IDOR enumeration of FERPA-protected records).
    """
    obj = model.query.get_or_404(obj_id)
    if getattr(current_user, 'role', None) != 'admin' \
            and getattr(obj, owner_attr, None) != current_user.id:
        abort(404)
    return obj


def caseload_student_or_404(student_id, allow_none=False):
    """Validate a request-supplied student_id belongs to the current caseload.

    Use on every create/update path that persists a student_id from form/JSON
    input, so a counselor can't attach a note/goal/referral/etc. to (and then
    view the name of) another counselor's student or a shadow student. Admins
    bypass. Returns the Student, or None when allow_none and no id was given;
    otherwise aborts 404 (no IDOR enumeration).
    """
    from app.models.student import Student
    if student_id in (None, '', 0, '0'):
        if allow_none:
            return None
        abort(404)
    try:
        sid = int(student_id)
    except (TypeError, ValueError):
        abort(404)
    return owned_or_404(Student, sid, owner_attr='assigned_counselor_id')

