from app import db
from datetime import datetime, timezone


class ImportLog(db.Model):
    """Tracks each data import with type, counts, and timestamp."""
    __tablename__ = 'import_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # What was imported
    import_type = db.Column(db.String(30), nullable=False)  # 'attendance', 'grades', 'student_update'
    grade_type = db.Column(db.String(10))  # 'final' or 'progress' (only for grades)
    school_year = db.Column(db.String(9))  # e.g., "2025-2026"
    quarter = db.Column(db.Integer)        # 1-4 (only for grades)

    # Results
    records_added = db.Column(db.Integer, default=0)
    records_updated = db.Column(db.Integer, default=0)
    records_skipped = db.Column(db.Integer, default=0)
    errors_count = db.Column(db.Integer, default=0)

    # When
    imported_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = db.relationship('User', backref=db.backref('import_logs', lazy='dynamic'))
