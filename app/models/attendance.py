from app import db
from datetime import datetime, timezone


class AttendanceRecord(db.Model):
    """Imported attendance data for trend analysis and early warning."""
    __tablename__ = 'attendance_records'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)

    # Period-level attendance
    date = db.Column(db.Date, nullable=False)
    period = db.Column(db.Integer)  # 1-4 for 4x4 schedule
    status = db.Column(db.String(20), nullable=False)  # present, absent, tardy, excused

    # Optional detail
    course_name = db.Column(db.String(200))
    reason = db.Column(db.String(200))

    # Metadata
    imported_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    imported_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Relationships
    student = db.relationship('Student', backref=db.backref(
        'attendance_records', lazy='dynamic', order_by='AttendanceRecord.date.desc()'
    ))
    imported_by = db.relationship('User', backref='attendance_imports')

    STATUSES = [
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('tardy', 'Tardy'),
        ('excused', 'Excused Absence'),
    ]
