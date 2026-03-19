from app import db
from datetime import datetime, timezone


class Note(db.Model):
    """Confidential counselor notes - FERPA protected."""
    __tablename__ = 'notes'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Note content
    note_type = db.Column(db.String(50), nullable=False)
    # Types: individual, group, parent_contact, teacher_consult, crisis, follow_up, referral, observation
    title = db.Column(db.String(200))
    content = db.Column(db.Text, nullable=False)

    # Session details
    session_date = db.Column(db.Date, default=lambda: datetime.now(timezone.utc).date())
    duration_minutes = db.Column(db.Integer)

    # ASCA alignment
    asca_domain = db.Column(db.String(50))  # academic, career, social_emotional
    asca_standard = db.Column(db.String(100))

    # Categorization
    topic_category = db.Column(db.String(100))
    delivery_method = db.Column(db.String(50))  # in_person, phone, email, virtual

    # Follow-up
    follow_up_needed = db.Column(db.Boolean, default=False)
    follow_up_date = db.Column(db.Date)
    follow_up_notes = db.Column(db.Text)
    follow_up_completed = db.Column(db.Boolean, default=False)

    # Confidentiality
    is_confidential = db.Column(db.Boolean, default=True)
    restricted_access = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    NOTE_TYPES = [
        ('individual', 'Individual Counseling'),
        ('group', 'Group Counseling'),
        ('parent_contact', 'Parent/Guardian Contact'),
        ('teacher_consult', 'Teacher Consultation'),
        ('crisis', 'Crisis Intervention'),
        ('follow_up', 'Follow-Up'),
        ('referral', 'Referral'),
        ('observation', 'Observation'),
        ('classroom', 'Classroom Lesson'),
        ('college_career', 'College & Career'),
        ('assessment', 'Assessment Review'),
    ]

    ASCA_DOMAINS = [
        ('academic', 'Academic Development'),
        ('career', 'Career Development'),
        ('social_emotional', 'Social/Emotional Development'),
    ]

    DELIVERY_METHODS = [
        ('in_person', 'In Person'),
        ('phone', 'Phone Call'),
        ('email', 'Email'),
        ('virtual', 'Virtual/Video'),
    ]
