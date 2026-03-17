from flask import request
from flask_login import current_user
from app import db
from app.models.user import AuditLog


def log_action(action, resource_type=None, resource_id=None, details=None):
    """Log an action for FERPA compliance audit trail."""
    entry = AuditLog(
        user_id=current_user.id if current_user and current_user.is_authenticated else None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=request.remote_addr if request else None,
    )
    db.session.add(entry)
    db.session.commit()
