from app import db
from datetime import datetime, timezone


class ServiceRecord(db.Model):
    """Student Service Log - chronological record of all services per student."""
    __tablename__ = 'service_records'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    counselor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    # Service details
    date = db.Column(db.Date, nullable=False, default=lambda: datetime.now(timezone.utc).date(), index=True)
    service_type = db.Column(db.String(50), nullable=False)
    topic = db.Column(db.String(200))
    description = db.Column(db.Text)
    duration_minutes = db.Column(db.Integer)

    # ASCA Domain
    asca_domain = db.Column(db.String(50))
    asca_standard = db.Column(db.String(100))

    # Delivery
    delivery_method = db.Column(db.String(50))
    setting = db.Column(db.String(50))  # office, classroom, hallway, phone, etc.

    # Outcome
    outcome = db.Column(db.Text)
    follow_up_required = db.Column(db.Boolean, default=False)
    follow_up_date = db.Column(db.Date)
    referral_made = db.Column(db.Boolean, default=False)
    referral_to = db.Column(db.String(200))

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    counselor = db.relationship('User', backref='service_records')

    SERVICE_TYPES = [
        ('individual_counseling', 'Individual Counseling'),
        ('group_counseling', 'Group Counseling'),
        ('crisis_intervention', 'Crisis Intervention'),
        ('classroom_lesson', 'Classroom Guidance Lesson'),
        ('consultation', 'Consultation'),
        ('parent_conference', 'Parent/Guardian Conference'),
        ('college_career', 'College & Career Planning'),
        ('academic_planning', 'Academic Planning'),
        ('referral', 'Referral'),
        ('assessment', 'Assessment'),
        ('observation', 'Observation'),
        ('follow_up', 'Follow-Up'),
        ('mediation', 'Mediation/Conflict Resolution'),
        ('504_iep', '504/IEP Meeting'),
        ('schedule_change', 'Schedule Change'),
    ]
