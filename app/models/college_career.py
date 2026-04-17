from app import db
from datetime import datetime, timezone


class CollegeCareerPlan(db.Model):
    __tablename__ = 'college_career_plans'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), unique=True, index=True, nullable=False)
    counselor_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)

    pathway = db.Column(db.String(30), default='undecided')
    intended_major = db.Column(db.String(200))
    career_interest = db.Column(db.String(200))

    gpa_weighted = db.Column(db.Float)
    gpa_unweighted = db.Column(db.Float)

    sat_total = db.Column(db.Integer)
    sat_reading = db.Column(db.Integer)
    sat_math = db.Column(db.Integer)
    act_composite = db.Column(db.Integer)

    fafsa_status = db.Column(db.String(20), default='not_started')
    fafsa_submitted_date = db.Column(db.Date)
    css_profile_status = db.Column(db.String(20), default='not_needed')
    dream_act_status = db.Column(db.String(20), default='not_needed')

    personal_statement_status = db.Column(db.String(20), default='not_started')
    letters_of_rec_requested = db.Column(db.Integer, default=0)
    letters_of_rec_received = db.Column(db.Integer, default=0)
    transcript_sent = db.Column(db.Boolean, default=False)

    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    student = db.relationship('Student', backref=db.backref('college_career_plan', uselist=False))
    counselor = db.relationship('User', backref='college_career_plans')
    applications = db.relationship('CollegeApplication', backref='plan', lazy='dynamic',
                                   cascade='all, delete-orphan',
                                   order_by='CollegeApplication.deadline')
    test_scores = db.relationship('TestScore', backref='plan', lazy='dynamic',
                                  cascade='all, delete-orphan',
                                  order_by='TestScore.test_date.desc()')

    PATHWAYS = [
        ('undecided', 'Undecided'),
        ('4year', '4-Year University'),
        ('2year', 'Community College'),
        ('cte_trade', 'CTE / Trade School'),
        ('military', 'Military'),
        ('workforce', 'Direct to Workforce'),
    ]

    FAFSA_STATUSES = [
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('submitted', 'Submitted'),
        ('verified', 'Verified'),
    ]

    AID_STATUSES = [
        ('not_needed', 'Not Needed'),
        ('not_started', 'Not Started'),
        ('submitted', 'Submitted'),
    ]

    STATEMENT_STATUSES = [
        ('not_started', 'Not Started'),
        ('drafting', 'Drafting'),
        ('reviewed', 'Reviewed by Counselor'),
        ('final', 'Final'),
    ]

    @property
    def pathway_label(self):
        return dict(self.PATHWAYS).get(self.pathway, 'Undecided')

    @property
    def fafsa_label(self):
        return dict(self.FAFSA_STATUSES).get(self.fafsa_status, 'Not Started')

    @property
    def statement_label(self):
        return dict(self.STATEMENT_STATUSES).get(self.personal_statement_status, 'Not Started')

    @property
    def apps_submitted(self):
        return self.applications.filter(
            CollegeApplication.status.in_(['submitted', 'accepted', 'denied', 'waitlisted', 'committed'])
        ).count()

    @property
    def apps_total(self):
        return self.applications.count()

    @property
    def apps_accepted(self):
        return self.applications.filter_by(status='accepted').count()

    @property
    def committed_college(self):
        c = self.applications.filter_by(status='committed').first()
        return c.college_name if c else None

    @property
    def best_test_display(self):
        parts = []
        if self.sat_total:
            parts.append(f"SAT {self.sat_total}")
        if self.act_composite:
            parts.append(f"ACT {self.act_composite}")
        return ' / '.join(parts) if parts else None


class CollegeApplication(db.Model):
    __tablename__ = 'college_applications'

    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('college_career_plans.id'), index=True, nullable=False)

    college_name = db.Column(db.String(200), nullable=False)
    college_type = db.Column(db.String(30))
    application_type = db.Column(db.String(30))
    status = db.Column(db.String(20), default='planned')
    deadline = db.Column(db.Date)
    submitted_date = db.Column(db.Date)
    decision_date = db.Column(db.Date)
    financial_aid_offered = db.Column(db.Float)
    notes = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    COLLEGE_TYPES = [
        ('uc', 'UC'),
        ('csu', 'CSU'),
        ('private', 'Private'),
        ('community_college', 'Community College'),
        ('out_of_state', 'Out of State'),
        ('trade', 'Trade / Technical'),
    ]

    APP_TYPES = [
        ('early_decision', 'Early Decision'),
        ('early_action', 'Early Action'),
        ('regular', 'Regular Decision'),
        ('rolling', 'Rolling'),
    ]

    STATUSES = [
        ('planned', 'Planned'),
        ('in_progress', 'In Progress'),
        ('submitted', 'Submitted'),
        ('accepted', 'Accepted'),
        ('denied', 'Denied'),
        ('waitlisted', 'Waitlisted'),
        ('committed', 'Committed'),
    ]

    @property
    def college_type_label(self):
        return dict(self.COLLEGE_TYPES).get(self.college_type, self.college_type or '')

    @property
    def app_type_label(self):
        return dict(self.APP_TYPES).get(self.application_type, self.application_type or '')

    @property
    def status_label(self):
        return dict(self.STATUSES).get(self.status, self.status or '')


class TestScore(db.Model):
    __tablename__ = 'test_scores'

    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('college_career_plans.id'), index=True, nullable=False)

    test_type = db.Column(db.String(20), nullable=False)
    test_name = db.Column(db.String(100))
    test_date = db.Column(db.Date)
    score = db.Column(db.String(20))
    score_detail = db.Column(db.String(200))

    TEST_TYPES = [
        ('sat', 'SAT'),
        ('act', 'ACT'),
        ('psat', 'PSAT/NMSQT'),
        ('ap', 'AP Exam'),
        ('ib', 'IB Exam'),
    ]

    @property
    def test_type_label(self):
        return dict(self.TEST_TYPES).get(self.test_type, self.test_type or '')

    @property
    def display_name(self):
        if self.test_name:
            return f"{self.test_type_label}: {self.test_name}"
        return self.test_type_label
