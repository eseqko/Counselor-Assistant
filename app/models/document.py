from app import db
from datetime import datetime, timezone


class StudentDocument(db.Model):
    """Generic document storage for student files (transcripts, court orders, IEPs, etc.)."""
    __tablename__ = 'student_documents'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    counselor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    document_type = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text)

    filename = db.Column(db.String(300), nullable=False)
    original_filename = db.Column(db.String(300))
    file_size = db.Column(db.Integer)
    mime_type = db.Column(db.String(100))

    document_date = db.Column(db.Date)
    expiration_date = db.Column(db.Date)
    is_confidential = db.Column(db.Boolean, default=True)

    tags = db.Column(db.String(300))

    uploaded_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    counselor = db.relationship('User', backref='student_documents')
    student = db.relationship('Student', backref=db.backref('documents', lazy='dynamic',
                              order_by='StudentDocument.uploaded_at.desc()'))

    DOCUMENT_TYPES = [
        ('transcript', 'Transcript / Report Card'),
        ('iep', 'IEP'),
        ('504', '504 Plan'),
        ('test_report', 'Test Report (assessment)'),
        ('medical', 'Medical / Health Record'),
        ('court_order', 'Court Order / Custody'),
        ('birth_cert', 'Birth Certificate / ID'),
        ('immunization', 'Immunization Records'),
        ('consent_form', 'Signed Consent Form'),
        ('correspondence', 'Letter / Correspondence'),
        ('referral_paperwork', 'Referral Paperwork'),
        ('graduation_audit', 'Graduation Audit'),
        ('college_letter', 'College Acceptance / Letter'),
        ('other', 'Other'),
    ]

    @property
    def type_label(self):
        return dict(self.DOCUMENT_TYPES).get(self.document_type, self.document_type)
