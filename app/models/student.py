from app import db
from datetime import datetime, timezone


# Association table for student tags
student_tags = db.Table('student_tags',
    db.Column('student_id', db.Integer, db.ForeignKey('students.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tags.id'), primary_key=True)
)


class Student(db.Model):
    __tablename__ = 'students'

    id = db.Column(db.Integer, primary_key=True)
    student_id_number = db.Column(db.String(50), unique=True, nullable=False)  # School ID number
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    grade_level = db.Column(db.Integer)
    date_of_birth = db.Column(db.Date)
    gender = db.Column(db.String(20))
    ethnicity = db.Column(db.String(50))
    email = db.Column(db.String(200))
    phone = db.Column(db.String(20))
    parent_guardian_name = db.Column(db.String(200))
    parent_guardian_phone = db.Column(db.String(20))
    parent_guardian_email = db.Column(db.String(200))
    address = db.Column(db.Text)
    homeroom = db.Column(db.String(50))

    # Counselor assignment
    assigned_counselor_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Status
    status = db.Column(db.String(20), default='active')  # active, inactive, transferred, graduated
    enrollment_date = db.Column(db.Date)
    iep_status = db.Column(db.Boolean, default=False)
    section_504 = db.Column(db.Boolean, default=False)
    ell_status = db.Column(db.Boolean, default=False)

    # Special programs
    special_programs = db.Column(db.Text)  # JSON list of programs
    notes_text = db.Column(db.Text)  # Quick notes field

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    assigned_counselor = db.relationship('User', backref='assigned_students')
    tags = db.relationship('Tag', secondary=student_tags, backref='students')
    notes = db.relationship('Note', backref='student', lazy='dynamic',
                           order_by='Note.created_at.desc()')
    service_records = db.relationship('ServiceRecord', backref='student', lazy='dynamic',
                                     order_by='ServiceRecord.date.desc()')

    @property
    def full_name(self):
        return f"{self.last_name}, {self.first_name}"

    @property
    def display_name(self):
        return f"{self.first_name} {self.last_name}"


class Tag(db.Model):
    __tablename__ = 'tags'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    color = db.Column(db.String(7), default='#6c757d')  # hex color
