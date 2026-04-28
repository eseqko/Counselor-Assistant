from app import db
from datetime import datetime, timezone


class InterventionPlan(db.Model):
    """MTSS/RTI Intervention Plan with tier, strategy, and progress monitoring."""
    __tablename__ = 'intervention_plans'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    counselor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    tier = db.Column(db.Integer, default=1, nullable=False, index=True)  # 1, 2, 3
    concern_area = db.Column(db.String(100), nullable=False)
    concern_details = db.Column(db.Text)

    strategy = db.Column(db.Text, nullable=False)
    frequency = db.Column(db.String(100))
    duration = db.Column(db.String(100))
    location = db.Column(db.String(100))
    interventionist = db.Column(db.String(200))

    success_criteria = db.Column(db.Text)
    baseline_data = db.Column(db.Text)

    # Optional links to other tracking
    linked_goal_id = db.Column(db.Integer, db.ForeignKey('goals.id'), nullable=True)
    linked_group_id = db.Column(db.Integer, db.ForeignKey('counseling_groups.id'), nullable=True)
    linked_referral_id = db.Column(db.Integer, db.ForeignKey('referrals.id'), nullable=True)

    start_date = db.Column(db.Date, default=lambda: datetime.now(timezone.utc).date())
    review_date = db.Column(db.Date, index=True)
    end_date = db.Column(db.Date)

    status = db.Column(db.String(20), default='active', index=True)
    outcome = db.Column(db.Text)
    next_steps = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    counselor = db.relationship('User', backref='intervention_plans')
    student = db.relationship('Student', backref=db.backref('interventions', lazy='dynamic',
                              order_by='InterventionPlan.start_date.desc()'))
    progress_entries = db.relationship('InterventionProgress', backref='plan',
                                       cascade='all, delete-orphan',
                                       order_by='InterventionProgress.entry_date.desc()')
    linked_goal = db.relationship('Goal')
    linked_group = db.relationship('CounselingGroup')
    linked_referral = db.relationship('Referral')

    TIERS = [
        (1, 'Tier 1 - Universal'),
        (2, 'Tier 2 - Targeted'),
        (3, 'Tier 3 - Intensive'),
    ]

    CONCERN_AREAS = [
        ('academic', 'Academic'),
        ('attendance', 'Attendance'),
        ('behavior', 'Behavior'),
        ('social_emotional', 'Social/Emotional'),
        ('executive_function', 'Executive Function'),
        ('peer_relationships', 'Peer Relationships'),
        ('mental_health', 'Mental Health'),
        ('engagement', 'Engagement'),
        ('other', 'Other'),
    ]

    STATUSES = [
        ('active', 'Active'),
        ('successful', 'Successful - Exit'),
        ('continued', 'Continued at Tier'),
        ('escalated', 'Escalated to Higher Tier'),
        ('discontinued', 'Discontinued'),
    ]

    DATA_SOURCES = [
        ('teacher_report', 'Teacher Report'),
        ('grades', 'Grades'),
        ('attendance', 'Attendance'),
        ('behavior_log', 'Behavior Log'),
        ('observation', 'Observation'),
        ('self_report', 'Self-Report'),
        ('screener', 'Screener Score'),
        ('other', 'Other'),
    ]

    @property
    def tier_label(self):
        return dict(self.TIERS).get(self.tier, f'Tier {self.tier}')


class InterventionProgress(db.Model):
    __tablename__ = 'intervention_progress'

    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('intervention_plans.id'), nullable=False, index=True)

    entry_date = db.Column(db.Date, nullable=False, default=lambda: datetime.now(timezone.utc).date())
    metric_value = db.Column(db.String(200))
    data_source = db.Column(db.String(40))
    note = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
