from app import db
from datetime import datetime, timezone


class IEP504Record(db.Model):
    __tablename__ = 'iep504_records'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'),
                           unique=True, nullable=False)
    counselor_id = db.Column(db.Integer, db.ForeignKey('users.id'),
                             nullable=False)
    plan_type = db.Column(db.String(10), nullable=False)  # 'iep' or '504'
    next_review_date = db.Column(db.Date)
    accommodations_text = db.Column(db.Text)
    document_filename = db.Column(db.String(255))
    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime,
                           default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime,
                           default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    student = db.relationship('Student', backref=db.backref(
        'iep504_record', uselist=False))
    counselor = db.relationship('User', backref='iep504_records')

    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'student_name': self.student.full_name if self.student else '',
            'student_display_name': self.student.display_name if self.student else '',
            'student_id_number': self.student.student_id_number if self.student else '',
            'grade_level': self.student.grade_level if self.student else None,
            'plan_type': self.plan_type,
            'next_review_date': self.next_review_date.isoformat() if self.next_review_date else None,
            'accommodations_text': self.accommodations_text or '',
            'document_filename': self.document_filename,
            'notes': self.notes or '',
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
