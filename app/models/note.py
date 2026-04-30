from app import db
from datetime import datetime, timezone


class Note(db.Model):
    """Unified counselor notes — replaces both Student Notes and Service Records.
    Maps to Synergy Conference Note categories. FERPA protected."""
    __tablename__ = 'notes'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    # Note content
    note_type = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(200))
    content = db.Column(db.Text, nullable=False)
    private_comment = db.Column(db.Text)

    # Session details
    session_date = db.Column(db.Date, default=lambda: datetime.now(timezone.utc).date(), index=True)
    duration_minutes = db.Column(db.Integer)

    # ASCA alignment
    asca_domain = db.Column(db.String(50))
    asca_standard = db.Column(db.String(100))

    # Categorization
    topic_category = db.Column(db.String(100))
    delivery_method = db.Column(db.String(50))
    setting = db.Column(db.String(50))

    # Outcome / referral (merged from ServiceRecord)
    outcome = db.Column(db.Text)
    referred_by = db.Column(db.String(200))
    referral_made = db.Column(db.Boolean, default=False)
    referral_to = db.Column(db.String(200))

    # Follow-up
    follow_up_needed = db.Column(db.Boolean, default=False)
    follow_up_date = db.Column(db.Date)
    follow_up_notes = db.Column(db.Text)
    follow_up_completed = db.Column(db.Boolean, default=False)
    follow_up_completed_date = db.Column(db.Date)

    # Confidentiality
    is_confidential = db.Column(db.Boolean, default=True)
    restricted_access = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    # Categories matching Synergy Conference Notes "Description" dropdown
    NOTE_TYPES = [
        ('504_plan', '504 Plan'),
        ('academic', 'Academic'),
        ('admin_notes', 'Admin Notes'),
        ('alternative_education', 'Alternative Education'),
        ('attendance', 'Attendance'),
        ('behavior', 'Behavior'),
        ('classroom_presentation', 'Classroom Presentation'),
        ('college_career', 'College/Career Planning'),
        ('eld_program', 'ELD Program'),
        ('enrollment', 'Enrollment'),
        ('financial_aid', 'Financial Aid'),
        ('four_year_plan', 'Four-Year Plan/Graduation'),
        ('group_counseling', 'Group Counseling'),
        ('inspire', 'INSPIRE'),
        ('no_show', 'No Show'),
        ('parent_guardian_contact', 'Parent/Guardian Contact'),
        ('referral', 'Referral to Community Resources'),
        ('restorative_meeting', 'Restorative Meeting'),
        ('scheduling', 'Scheduling'),
        ('social_emotional', 'Social/Emotional Counseling'),
        ('sped_program', 'SPED Program'),
        ('staff_concerns', 'Staff Concerns/Meetings'),
        ('student_conference', 'Student Conference'),
        ('student_study_team', 'Student Study Team'),
        ('crisis', 'Crisis Intervention'),
        ('observation', 'Observation'),
        ('assessment', 'Assessment Review'),
        ('mediation', 'Mediation/Conflict Resolution'),
        ('schedule_change', 'Schedule Change'),
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
