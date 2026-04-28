from app import db
from datetime import datetime, timezone


class Goal(db.Model):
    """SMART goals for students — aligns with ASCA Mindsets & Behaviors."""
    __tablename__ = 'goals'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    counselor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)

    asca_domain = db.Column(db.String(50))
    asca_mindset = db.Column(db.String(100))

    # SMART specifics
    baseline = db.Column(db.String(200))
    target = db.Column(db.String(200))
    measurement_method = db.Column(db.String(200))
    strategy = db.Column(db.Text)

    start_date = db.Column(db.Date, default=lambda: datetime.now(timezone.utc).date())
    target_date = db.Column(db.Date, index=True)
    completed_date = db.Column(db.Date)

    status = db.Column(db.String(20), default='active', index=True)
    progress_percent = db.Column(db.Integer, default=0)
    outcome = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    counselor = db.relationship('User', backref='goals')
    student = db.relationship('Student', backref=db.backref('goals', lazy='dynamic',
                              order_by='Goal.target_date'))
    progress_entries = db.relationship('GoalProgress', backref='goal',
                                       cascade='all, delete-orphan',
                                       order_by='GoalProgress.entry_date.desc()')

    ASCA_DOMAINS = [
        ('academic', 'Academic Development'),
        ('career', 'Career Development'),
        ('social_emotional', 'Social/Emotional Development'),
    ]

    STATUSES = [
        ('active', 'Active'),
        ('in_progress', 'In Progress'),
        ('achieved', 'Achieved'),
        ('not_met', 'Not Met'),
        ('cancelled', 'Cancelled'),
    ]

    @property
    def status_label(self):
        return dict(self.STATUSES).get(self.status, self.status)

    @property
    def domain_label(self):
        return dict(self.ASCA_DOMAINS).get(self.asca_domain, self.asca_domain or '')

    @property
    def is_open(self):
        return self.status in ('active', 'in_progress')


class GoalProgress(db.Model):
    """Tracking entries for goal progress over time."""
    __tablename__ = 'goal_progress'

    id = db.Column(db.Integer, primary_key=True)
    goal_id = db.Column(db.Integer, db.ForeignKey('goals.id'), nullable=False, index=True)

    entry_date = db.Column(db.Date, nullable=False, default=lambda: datetime.now(timezone.utc).date())
    metric_value = db.Column(db.String(200))
    progress_percent = db.Column(db.Integer)
    note = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
