from flask import request, current_app
from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@login_manager.request_loader
def load_user_from_device_token(req):
    """Authenticate requests via device_token cookie."""
    token = req.cookies.get('device_token')
    if not token:
        return None
    from app.models.device import DeviceToken
    device = DeviceToken.lookup(token, current_app.config['SECRET_KEY'])
    if device:
        device.last_used_at = datetime.now(timezone.utc)
        device.last_ip = req.remote_addr
        db.session.commit()
        req.device_token = device
        return User.query.get(device.user_id)
    return None


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    display_name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), default='counselor')  # counselor, admin
    school_name = db.Column(db.String(200), default='')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_login = db.Column(db.DateTime)

    # Relationships
    notes = db.relationship('Note', backref='author', lazy='dynamic')
    activities = db.relationship('Activity', backref='counselor', lazy='dynamic')
    calendar_events = db.relationship('CalendarEvent', backref='owner', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class AuditLog(db.Model):
    """FERPA-compliant audit logging for all data access."""
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    action = db.Column(db.String(50), nullable=False)  # view, create, update, delete, export
    resource_type = db.Column(db.String(50))  # student, note, report, etc.
    resource_id = db.Column(db.Integer)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    device_token_id = db.Column(db.Integer, db.ForeignKey('device_tokens.id'), nullable=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref='audit_logs')
    device_token = db.relationship('DeviceToken')
