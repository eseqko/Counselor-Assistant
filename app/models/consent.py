from app import db
from datetime import datetime, timezone


class ConsentRecord(db.Model):
    """Parent consent for counseling services, groups, referrals, screenings, etc."""
    __tablename__ = 'consent_records'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    counselor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    consent_type = db.Column(db.String(50), nullable=False, index=True)
    description = db.Column(db.Text)

    guardian_name = db.Column(db.String(200))
    guardian_relationship = db.Column(db.String(50))
    guardian_phone = db.Column(db.String(40))
    guardian_email = db.Column(db.String(200))

    request_date = db.Column(db.Date, default=lambda: datetime.now(timezone.utc).date())
    received_date = db.Column(db.Date)
    expiration_date = db.Column(db.Date, index=True)

    status = db.Column(db.String(20), default='requested', index=True)
    method = db.Column(db.String(40))
    document_filename = db.Column(db.String(300))

    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    counselor = db.relationship('User', backref='consents')
    student = db.relationship('Student', backref=db.backref('consents', lazy='dynamic',
                              order_by='ConsentRecord.created_at.desc()'))

    CONSENT_TYPES = [
        ('counseling_services', 'General Counseling Services'),
        ('group_counseling', 'Group Counseling'),
        ('individual_counseling', 'Individual Counseling'),
        ('mental_health_referral', 'Mental Health Referral'),
        ('screening', 'Mental Health Screening'),
        ('records_release', 'Records Release'),
        ('photo_video', 'Photo / Video'),
        ('field_trip', 'Field Trip / Off-Site'),
        ('information_share', 'Information Sharing'),
        ('other', 'Other'),
    ]

    METHODS = [
        ('paper', 'Paper Form'),
        ('electronic', 'Electronic'),
        ('verbal', 'Verbal (documented)'),
        ('email', 'Email'),
    ]

    STATUSES = [
        ('requested', 'Requested'),
        ('received', 'Received'),
        ('declined', 'Declined'),
        ('expired', 'Expired'),
        ('revoked', 'Revoked'),
    ]

    GUARDIAN_RELATIONSHIPS = [
        ('mother', 'Mother'),
        ('father', 'Father'),
        ('parent', 'Parent'),
        ('guardian', 'Guardian'),
        ('grandparent', 'Grandparent'),
        ('foster', 'Foster Parent'),
        ('other', 'Other'),
    ]

    @property
    def consent_type_label(self):
        return dict(self.CONSENT_TYPES).get(self.consent_type, self.consent_type)

    @property
    def status_label(self):
        return dict(self.STATUSES).get(self.status, self.status)

    @property
    def is_active(self):
        from datetime import date
        if self.status != 'received':
            return False
        if self.expiration_date and self.expiration_date < date.today():
            return False
        return True
