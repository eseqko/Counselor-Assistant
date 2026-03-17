import hmac
import hashlib
import secrets
from app import db
from datetime import datetime, timezone, timedelta


class DeviceInvite(db.Model):
    """One-time invite code for registering a new device."""
    __tablename__ = 'device_invites'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)
    used_at = db.Column(db.DateTime, nullable=True)

    created_by = db.relationship('User', backref='device_invites')

    @staticmethod
    def generate(user_id, hours=24):
        """Create a new invite valid for the given number of hours."""
        invite = DeviceInvite(
            code=secrets.token_urlsafe(32),
            created_by_id=user_id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=hours),
        )
        db.session.add(invite)
        db.session.commit()
        return invite

    @property
    def is_valid(self):
        return not self.used and datetime.now(timezone.utc) < self.expires_at


class DeviceToken(db.Model):
    """A registered device with persistent access."""
    __tablename__ = 'device_tokens'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    device_name = db.Column(db.String(120), nullable=False)
    token_hash = db.Column(db.String(256), nullable=False, unique=True)
    token_prefix = db.Column(db.String(8))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_used_at = db.Column(db.DateTime, nullable=True)
    last_ip = db.Column(db.String(45), nullable=True)
    is_revoked = db.Column(db.Boolean, default=False)
    invite_id = db.Column(db.Integer, db.ForeignKey('device_invites.id'), nullable=True)

    user = db.relationship('User', backref='device_tokens')
    invite = db.relationship('DeviceInvite', backref='device_token')

    @staticmethod
    def create(user_id, device_name, secret_key, invite_id=None):
        """Create a new device token. Returns (DeviceToken, plain_token)."""
        plain_token = secrets.token_urlsafe(48)
        token_hash = DeviceToken.hash_token(plain_token, secret_key)
        device = DeviceToken(
            user_id=user_id,
            device_name=device_name,
            token_hash=token_hash,
            token_prefix=plain_token[:8],
            invite_id=invite_id,
        )
        db.session.add(device)
        db.session.commit()
        return device, plain_token

    @staticmethod
    def hash_token(plain_token, secret_key):
        """HMAC-SHA256 hash of a token using the app secret key."""
        return hmac.new(
            secret_key.encode(), plain_token.encode(), hashlib.sha256
        ).hexdigest()

    @staticmethod
    def lookup(plain_token, secret_key):
        """Find a valid (non-revoked) device by token."""
        token_hash = DeviceToken.hash_token(plain_token, secret_key)
        return DeviceToken.query.filter_by(
            token_hash=token_hash, is_revoked=False
        ).first()
