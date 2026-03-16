from app import db
from datetime import datetime, timezone


class Department(db.Model):
    __tablename__ = 'departments'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    head = db.Column(db.String(100))
    color = db.Column(db.String(7), default='#4A90D9')
    sort_order = db.Column(db.Integer, default=0)

    courses = db.relationship('Course', backref='department', lazy='dynamic',
                             order_by='Course.course_number')


class Course(db.Model):
    """Course Catalog Wiki - comprehensive course reference for advisement."""
    __tablename__ = 'courses'

    id = db.Column(db.Integer, primary_key=True)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))

    # Course identification
    course_number = db.Column(db.String(20), unique=True, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)

    # Requirements
    credits = db.Column(db.Float, default=1.0)
    grade_levels = db.Column(db.String(50))  # e.g., "9,10,11,12"
    prerequisites = db.Column(db.Text)  # Course numbers, comma-separated
    corequisites = db.Column(db.Text)

    # Classification
    course_type = db.Column(db.String(50))
    # required, elective, honors, ap, ib, dual_enrollment, cte
    subject_area = db.Column(db.String(100))
    is_weighted = db.Column(db.Boolean, default=False)
    weight = db.Column(db.Float, default=0.0)  # GPA weight bonus

    # Graduation requirement
    meets_requirement = db.Column(db.String(200))  # Which grad requirements this satisfies
    ncaa_approved = db.Column(db.Boolean, default=False)

    # Details
    max_enrollment = db.Column(db.Integer)
    semesters = db.Column(db.Integer, default=2)  # 1=semester, 2=full year
    instructor = db.Column(db.String(100))
    room = db.Column(db.String(20))

    # Wiki-style content
    detailed_description = db.Column(db.Text)  # Rich text / markdown
    resources = db.Column(db.Text)  # Links to resources
    notes = db.Column(db.Text)  # Counselor notes about the course

    is_active = db.Column(db.Boolean, default=True)
    school_year = db.Column(db.String(9))  # e.g., "2025-2026"

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    COURSE_TYPES = [
        ('required', 'Required'),
        ('elective', 'Elective'),
        ('honors', 'Honors'),
        ('ap', 'AP'),
        ('ib', 'IB'),
        ('dual_enrollment', 'Dual Enrollment'),
        ('cte', 'CTE/Vocational'),
    ]


class GraduationRequirement(db.Model):
    """Track graduation requirements for advisement."""
    __tablename__ = 'graduation_requirements'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # e.g., "English", "Math"
    credits_required = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text)
    qualifying_courses = db.Column(db.Text)  # Course numbers that satisfy this
    sort_order = db.Column(db.Integer, default=0)
