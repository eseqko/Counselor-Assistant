"""Snapshot model for end-of-year caseload rollover undo.

When a counselor commits a rollover, the prior state of every affected student
is stored as JSON in this table. Within 24 hours they can hit "Undo" to restore.
"""
import json
from datetime import datetime, timedelta, timezone

from app import db


class RolloverSnapshot(db.Model):
    __tablename__ = 'rollover_snapshots'

    id = db.Column(db.Integer, primary_key=True)
    counselor_id = db.Column(db.Integer, db.ForeignKey('users.id'),
                             nullable=False, index=True)
    created_at = db.Column(db.DateTime,
                           default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime,
                           default=lambda: datetime.now(timezone.utc) + timedelta(hours=24))
    student_count = db.Column(db.Integer, default=0)
    school_year_end_date = db.Column(db.Date)
    payload = db.Column(db.Text, nullable=False)
    undone = db.Column(db.Boolean, default=False)
    undone_at = db.Column(db.DateTime)

    counselor = db.relationship('User', backref='rollover_snapshots')

    def items(self):
        """Decoded list of per-student snapshot entries."""
        return json.loads(self.payload) if self.payload else []

    def is_expired(self):
        if not self.expires_at:
            return False
        now = datetime.now(timezone.utc)
        # SQLite stores naive UTC; coerce for comparison
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return now >= exp

    def can_undo(self):
        return not self.undone and not self.is_expired()
