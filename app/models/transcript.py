from app import db
from datetime import datetime, timezone


class TranscriptRecord(db.Model):
    __tablename__ = 'transcript_records'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    import_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    quarter = db.Column(db.String(10))  # e.g., "11-Q3"

    # Graduation summary
    total_completed = db.Column(db.Float, default=0)
    total_wip = db.Column(db.Float, default=0)
    total_needed = db.Column(db.Float, default=0)
    risk_level = db.Column(db.String(20))  # critical, at-risk, warning, on-track

    # a-g summary
    ag_status = db.Column(db.String(20))  # deficient, verify, on-track
    ag_areas_met = db.Column(db.Integer, default=0)
    ag_areas_deficient = db.Column(db.Integer, default=0)

    # CTE summary
    cte_completed = db.Column(db.Float, default=0)
    cte_level = db.Column(db.String(20))  # none, explorer, concentrator, completer, advanced
    cte_is_completer = db.Column(db.Boolean, default=False)

    # Full data as JSON text
    credits_json = db.Column(db.Text)  # Full credit summary by subject
    ag_json = db.Column(db.Text)       # Full a-g area analysis

    # Metadata
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    student = db.relationship('Student', backref=db.backref(
        'transcript_records', lazy='dynamic', order_by='TranscriptRecord.import_date.desc()'
    ))
    created_by = db.relationship('User', backref='transcript_imports')
