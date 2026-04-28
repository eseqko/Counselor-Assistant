from app import db
from datetime import datetime, timezone


class ASCAProgram(db.Model):
    """ASCA Results / Closing-the-Gap program records."""
    __tablename__ = 'asca_programs'

    id = db.Column(db.Integer, primary_key=True)
    counselor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    name = db.Column(db.String(200), nullable=False)
    school_year = db.Column(db.String(20))
    asca_domain = db.Column(db.String(50))
    program_type = db.Column(db.String(40), default='results')  # results | closing_gap | annual

    target_group = db.Column(db.String(300))
    target_size = db.Column(db.Integer)

    # Goal language
    goal_statement = db.Column(db.Text)
    asca_standard = db.Column(db.String(200))

    # Baseline/outcome data
    baseline = db.Column(db.Text)
    intervention = db.Column(db.Text)
    outcome_data = db.Column(db.Text)
    process_data = db.Column(db.Text)
    perception_data = db.Column(db.Text)
    results_data = db.Column(db.Text)
    implications = db.Column(db.Text)

    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    status = db.Column(db.String(20), default='active', index=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    counselor = db.relationship('User', backref='asca_programs')

    PROGRAM_TYPES = [
        ('results', 'Results Report'),
        ('closing_gap', 'Closing-the-Gap'),
        ('annual', 'Annual Program Evaluation'),
    ]

    STATUSES = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('archived', 'Archived'),
    ]

    @property
    def type_label(self):
        return dict(self.PROGRAM_TYPES).get(self.program_type, self.program_type)
