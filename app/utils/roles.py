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


def admin_or_sole_user_required(f):
    """Decorator for whole-database actions (backup, export, import, reset).

    These routes hand out or destroy EVERY counselor's data, so in a shared
    deployment they must be admin-only. But a plain @admin_required would lock
    every existing install out of its own Backup button: the setup wizard and
    the bootstrap in app/__init__.py both create the primary user with
    role='counselor', and the only route that can grant 'admin' is itself
    @admin_required — so a single-counselor install has no admin and no way to
    make one.

    So: allow admins, OR allow when there is exactly one account, where that
    user necessarily owns all the data anyway. The moment a second account
    exists the gate becomes real. (setup.py now also promotes the primary user
    to admin, which fixes this going forward; this keeps already-installed
    single-user deployments working without a manual DB edit.)
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if getattr(current_user, 'role', None) != 'admin':
            from app.models.user import User
            if User.query.count() > 1:
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

