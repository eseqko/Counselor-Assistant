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
    assigned_counselor_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    # "Shadow" students are imported from grade/attendance files for school-wide
    # comparison reports but aren't on any counselor's caseload. Invisible to all
    # caseload UI (filtered out everywhere), surfaced only in aggregate analytics.
    is_shadow = db.Column(db.Boolean, default=False, index=True)
    # A per-counselor "Sample Student" for trying out screeners (and other tools)
    # without using a real student. Usable in tool dropdowns, but excluded from
    # caseload rosters, counts, and analytics so it never skews real data.
    is_sample = db.Column(db.Boolean, default=False, index=True)

    # Status
    status = db.Column(db.String(20), default='active', index=True)
    enrollment_date = db.Column(db.Date)
    exit_reason = db.Column(db.String(50))   # reason for removal from caseload
    exit_date = db.Column(db.Date)           # date student was removed
    exit_notes = db.Column(db.Text)          # optional additional context
    iep_status = db.Column(db.Boolean, default=False)
    section_504 = db.Column(db.Boolean, default=False)

    # EL Status - proper categories per California EL classification
    el_status = db.Column(db.String(20), default='EO')
    # EO = English Only, Newcomer, LTEL = Long-Term EL, RFEP = Reclassified Fluent English Proficient
    el_level = db.Column(db.String(10))  # EL 1, EL 2, EL 3 (only when Newcomer)

    # Keep legacy column for migration compatibility
    ell_status = db.Column(db.Boolean, default=False)

    # AB Graduation Exemption — California Ed Code special populations
    # Population flags (which bills the student qualifies under)
    is_foster_youth = db.Column(db.Boolean, default=False)       # AB 167/216
    is_homeless = db.Column(db.Boolean, default=False)           # AB 1806
    is_migrant_newcomer = db.Column(db.Boolean, default=False)   # AB 2121
    is_formerly_incarcerated = db.Column(db.Boolean, default=False)  # AB 2306/1124
    is_military_connected = db.Column(db.Boolean, default=False) # AB 365
    # Waiver status: none, eligible, accepted, declined
    ab_exemption_status = db.Column(db.String(20), default='none')
    ab_exemption_date = db.Column(db.Date)
    ab_transfer_date = db.Column(db.Date)

    # EL — Date First Enrolled in US Schools (from Ellevation "Enrolled in US" column).
    # Drives years_in_us_schools property and cohort filters in ELPAC analytics.
    us_school_entry_date = db.Column(db.Date)

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

    EXIT_REASONS = [
        ('graduated', 'Graduated'),
        ('transferred_in_district', 'Transferred (In-District)'),
        ('transferred_out_district', 'Transferred (Out of District)'),
        ('dropped_out', 'Dropped Out'),
        ('aged_out', 'Aged Out'),
        ('counselor_change', 'Reassigned to Another Counselor'),
        ('expelled', 'Expelled'),
        ('other', 'Other'),
    ]

    EL_STATUSES = [
        ('EO', 'EO - English Only'),
        ('Newcomer', 'Newcomer'),
        ('LTEL', 'LTEL - Long-Term English Learner'),
        ('RFEP', 'RFEP - Reclassified Fluent English Proficient'),
    ]

    EL_LEVELS = [
        ('EL 1', 'EL 1'),
        ('EL 2', 'EL 2'),
        ('EL 3', 'EL 3'),
    ]

    AB_EXEMPTION_STATUSES = [
        ('none', 'None'),
        ('eligible', 'Eligible — Not Yet Decided'),
        ('accepted', 'Accepted — Using State Minimum'),
        ('declined', 'Declined — Using District Requirements'),
    ]

    AB_POPULATION_FIELDS = [
        ('is_foster_youth', 'Foster Youth', 'AB 167/216'),
        ('is_homeless', 'Homeless', 'AB 1806'),
        ('is_migrant_newcomer', 'Migrant/Newcomer', 'AB 2121'),
        ('is_formerly_incarcerated', 'Formerly Incarcerated', 'AB 2306/1124'),
        ('is_military_connected', 'Military Connected', 'AB 365'),
    ]

    @property
    def full_name(self):
        return f"{self.last_name}, {self.first_name}"

    @property
    def display_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def is_el(self):
        return self.el_status in ('Newcomer', 'LTEL', 'RFEP')

    @property
    def el_display(self):
        if self.el_status == 'Newcomer' and self.el_level:
            return f"Newcomer ({self.el_level})"
        return self.el_status or 'EO'

    @property
    def has_ab_population(self):
        return any([self.is_foster_youth, self.is_homeless,
                     self.is_migrant_newcomer, self.is_formerly_incarcerated,
                     self.is_military_connected])

    @property
    def ab_bills(self):
        bills = []
        if self.is_foster_youth:
            bills.append('AB 167/216')
        if self.is_homeless:
            bills.append('AB 1806')
        if self.is_migrant_newcomer:
            bills.append('AB 2121')
        if self.is_formerly_incarcerated:
            bills.append('AB 2306/1124')
        if self.is_military_connected:
            bills.append('AB 365')
        return bills

    @property
    def uses_state_minimum(self):
        return self.ab_exemption_status == 'accepted'

    @property
    def latest_elpac(self):
        return self.elpac_scores.first()

    @property
    def is_rfep_eligible(self):
        latest = self.latest_elpac
        return bool(latest and latest.overall_level == 4)

    @property
    def years_in_us_schools(self):
        if not self.us_school_entry_date:
            return None
        from datetime import date
        return (date.today() - self.us_school_entry_date).days // 365

    @property
    def graduation_year(self):
        if not self.grade_level:
            return None
        from app.utils.helpers import current_school_year
        sy = current_school_year()
        end_year = int(sy.split('-')[1])
        return end_year + (12 - self.grade_level)


class Tag(db.Model):
    __tablename__ = 'tags'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    color = db.Column(db.String(7), default='#6c757d')  # hex color
