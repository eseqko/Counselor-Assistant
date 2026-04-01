from app import db
from datetime import datetime, timezone


class Activity(db.Model):
    """Activity log for tracking counselor time usage - ASCA aligned."""
    __tablename__ = 'activities'

    id = db.Column(db.Integer, primary_key=True)
    counselor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    # Activity details
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    date = db.Column(db.Date, nullable=False, default=lambda: datetime.now(timezone.utc).date(), index=True)
    start_time = db.Column(db.Time)
    end_time = db.Column(db.Time)
    duration_minutes = db.Column(db.Integer)

    # ASCA categorization
    service_type = db.Column(db.String(50), nullable=False)
    # direct_student, indirect_student, program_management, non_counseling
    category = db.Column(db.String(100))
    topic = db.Column(db.String(200))

    # Details
    delivery_type = db.Column(db.String(50))
    # individual, small_group, classroom, school_wide
    num_students = db.Column(db.Integer, default=0)
    grade_levels = db.Column(db.String(50))  # comma-separated

    # Recurring
    is_recurring = db.Column(db.Boolean, default=False)
    recurrence_pattern = db.Column(db.String(50))

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    SERVICE_TYPES = [
        ('direct_student', 'Direct Student Services'),
        ('indirect_student', 'Indirect Student Services'),
        ('program_management', 'Program Management & School Support'),
        ('non_counseling', 'Non-School Counseling Tasks'),
    ]

    CATEGORIES = {
        'direct_student': [
            ('individual_counseling', 'Individual Counseling'),
            ('group_counseling', 'Group Counseling'),
            ('classroom_instruction', 'Classroom Instruction/Guidance Lessons'),
            ('crisis_response', 'Crisis Response'),
            ('appraisal', 'Individual Student Planning - Appraisal'),
            ('advisement', 'Individual Student Planning - Advisement'),
        ],
        'indirect_student': [
            ('consultation', 'Consultation'),
            ('collaboration', 'Collaboration'),
            ('referrals', 'Referrals'),
            ('parent_outreach', 'Parent/Guardian Outreach'),
            ('teaming', 'Teaming'),
        ],
        'program_management': [
            ('program_planning', 'Program Planning'),
            ('data_analysis', 'Data Analysis'),
            ('curriculum_development', 'Curriculum/Materials Development'),
            ('professional_development', 'Professional Development'),
            ('school_committees', 'School Committees/Meetings'),
            ('fair_share', 'Fair-Share Responsibilities'),
        ],
        'non_counseling': [
            ('admin_tasks', 'Administrative Tasks'),
            ('clerical', 'Clerical Duties'),
            ('testing_coordination', 'Testing Coordination'),
            ('discipline', 'Discipline (non-counseling)'),
            ('scheduling_classes', 'Class Scheduling'),
            ('other_assigned', 'Other Assigned Duties'),
        ],
    }
