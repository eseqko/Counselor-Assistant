from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone
import secrets


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


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
    calendar_feed_token = db.Column(db.String(64), unique=True)
    external_ical_url = db.Column(db.String(500))
    school_config_json = db.Column(db.Text)  # JSON: school name, colors, mascot for catalog
    google_token_json = db.Column(db.Text)  # OAuth 2.0 token JSON for Google APIs
    setup_completed = db.Column(db.Boolean, default=False)  # First-run wizard completed
    theme_preference = db.Column(db.String(20), default='light')  # light, dark, auto, school, focus, fiesta, glass, glass-blue, glass-emerald
    reduced_motion = db.Column(db.Boolean, default=False)
    synergy_base_url = db.Column(db.String(500), default='')  # e.g. https://ca-juhsd.edupoint.com/
    alert_settings_json = db.Column(db.Text, default='')  # JSON: configurable alert thresholds

    # Relationships
    notes = db.relationship('Note', backref='author', lazy='dynamic')
    activities = db.relationship('Activity', backref='counselor', lazy='dynamic')
    calendar_events = db.relationship('CalendarEvent', backref='owner', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_or_create_feed_token(self):
        if not self.calendar_feed_token:
            self.calendar_feed_token = secrets.token_urlsafe(32)
            db.session.commit()
        return self.calendar_feed_token


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
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref='audit_logs')
