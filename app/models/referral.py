from app import db
from datetime import datetime, timezone


class Referral(db.Model):
    """Tracks formal referrals made for students with full status workflow."""
    __tablename__ = 'referrals'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    counselor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    # Optional link back to the service record that generated this referral
    service_record_id = db.Column(db.Integer, db.ForeignKey('service_records.id'), nullable=True)

    # Core referral info
    referral_date = db.Column(db.Date, nullable=False,
                              default=lambda: datetime.now(timezone.utc).date(), index=True)
    referral_type = db.Column(db.String(50), nullable=False)
    referred_to = db.Column(db.String(200), nullable=False)
    contact_info = db.Column(db.String(300))
    reason = db.Column(db.Text, nullable=False)
    urgency = db.Column(db.String(20), default='routine', index=True)

    # Status workflow
    status = db.Column(db.String(30), default='pending', nullable=False, index=True)
    contacted_date = db.Column(db.Date)
    accepted_date = db.Column(db.Date)
    completed_date = db.Column(db.Date)
    outcome = db.Column(db.Text)

    # Follow-up
    follow_up_date = db.Column(db.Date)
    follow_up_notes = db.Column(db.Text)

    # Confidentiality
    consent_obtained = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    counselor = db.relationship('User', backref='referrals')
    student = db.relationship('Student', backref=db.backref('referrals', lazy='dynamic',
                              order_by='Referral.referral_date.desc()'))
    service_record = db.relationship('ServiceRecord', backref='referrals')

    REFERRAL_TYPES = [
        ('mental_health', 'Mental Health / Therapy'),
        ('community_resource', 'Community Resource'),
        ('medical', 'Medical / Pediatrician'),
        ('psychiatric', 'Psychiatric Evaluation'),
        ('substance_abuse', 'Substance Abuse'),
        ('special_education', 'Special Education / SST'),
        ('504_plan', '504 Plan Evaluation'),
        ('cps_dcfs', 'CPS / Child Welfare'),
        ('law_enforcement', 'Law Enforcement / SRO'),
        ('academic_support', 'Academic Support / Tutoring'),
        ('attendance', 'Attendance / Truancy'),
        ('housing', 'Housing / McKinney-Vento'),
        ('food_assistance', 'Food Assistance'),
        ('legal_aid', 'Legal Aid'),
        ('career_services', 'Career / Workforce'),
        ('college_advising', 'College Advising'),
        ('peer_mentor', 'Peer Mentor / Group'),
        ('teacher_consult', 'Teacher / Staff Support'),
        ('other', 'Other'),
    ]

    URGENCY_LEVELS = [
        ('emergency', 'Emergency'),
        ('urgent', 'Urgent (24-48 hr)'),
        ('routine', 'Routine'),
        ('low', 'Low Priority'),
    ]

    STATUSES = [
        ('pending', 'Pending'),
        ('contacted', 'Contacted'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('no_show', 'No Show'),
        ('declined', 'Declined'),
        ('cancelled', 'Cancelled'),
    ]

    @property
    def is_open(self):
        return self.status in ('pending', 'contacted', 'in_progress')

    @property
    def status_label(self):
        return dict(self.STATUSES).get(self.status, self.status)

    @property
    def type_label(self):
        return dict(self.REFERRAL_TYPES).get(self.referral_type, self.referral_type)

    @property
    def urgency_label(self):
        return dict(self.URGENCY_LEVELS).get(self.urgency, self.urgency)
