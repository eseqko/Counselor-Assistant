from app import db
from datetime import datetime, timezone


class CommunicationLog(db.Model):
    """Unified log of contacts: parent calls, emails, meetings, etc."""
    __tablename__ = 'communication_logs'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=True, index=True)
    counselor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    contact_date = db.Column(db.Date, nullable=False,
                             default=lambda: datetime.now(timezone.utc).date(), index=True)
    contact_type = db.Column(db.String(40), nullable=False)
    direction = db.Column(db.String(20), default='outgoing')

    contact_person = db.Column(db.String(200), nullable=False)
    contact_role = db.Column(db.String(50))
    contact_email = db.Column(db.String(200))
    contact_phone = db.Column(db.String(40))

    subject = db.Column(db.String(300))
    summary = db.Column(db.Text)
    duration_minutes = db.Column(db.Integer)

    # Follow-up
    follow_up_needed = db.Column(db.Boolean, default=False)
    follow_up_date = db.Column(db.Date)
    follow_up_notes = db.Column(db.Text)
    follow_up_completed = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    counselor = db.relationship('User', backref='communications')
    student = db.relationship('Student', backref=db.backref('communications', lazy='dynamic',
                              order_by='CommunicationLog.contact_date.desc()'))

    CONTACT_TYPES = [
        ('phone', 'Phone Call'),
        ('email', 'Email'),
        ('text', 'Text / SMS'),
        ('meeting', 'In-Person Meeting'),
        ('virtual', 'Virtual Meeting'),
        ('letter', 'Letter / Mail'),
        ('home_visit', 'Home Visit'),
        ('voicemail', 'Voicemail Left'),
        ('attempted', 'Attempted Contact'),
    ]

    DIRECTIONS = [
        ('outgoing', 'Outgoing'),
        ('incoming', 'Incoming'),
    ]

    CONTACT_ROLES = [
        ('parent_guardian', 'Parent / Guardian'),
        ('teacher', 'Teacher'),
        ('administrator', 'Administrator'),
        ('outside_provider', 'Outside Provider'),
        ('agency', 'Agency / Community Org'),
        ('student', 'Student'),
        ('other', 'Other'),
    ]

    @property
    def type_label(self):
        return dict(self.CONTACT_TYPES).get(self.contact_type, self.contact_type)

    @property
    def role_label(self):
        return dict(self.CONTACT_ROLES).get(self.contact_role, self.contact_role or '')
