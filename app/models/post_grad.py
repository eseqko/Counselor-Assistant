from app import db
from datetime import datetime, timezone


class PostGradOutcome(db.Model):
    """Track what graduates ended up doing after high school."""
    __tablename__ = 'post_grad_outcomes'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, unique=True, index=True)
    counselor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    graduation_year = db.Column(db.Integer, index=True)
    graduation_date = db.Column(db.Date)

    primary_pathway = db.Column(db.String(40), nullable=False, index=True)
    institution_name = db.Column(db.String(300))
    program_major = db.Column(db.String(200))
    job_title = db.Column(db.String(200))
    employer = db.Column(db.String(200))
    military_branch = db.Column(db.String(50))

    # Status follow-up
    status_at_6mo = db.Column(db.String(40))
    status_at_1yr = db.Column(db.String(40))
    status_at_2yr = db.Column(db.String(40))

    enrollment_verified = db.Column(db.Boolean, default=False)
    completed_credential = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text)

    contact_email = db.Column(db.String(200))
    contact_phone = db.Column(db.String(40))

    last_followup_date = db.Column(db.Date)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    counselor = db.relationship('User', backref='post_grad_outcomes')
    student = db.relationship('Student', backref=db.backref('post_grad_outcome', uselist=False))

    PATHWAYS = [
        ('4year_college', '4-Year College/University'),
        ('2year_college', '2-Year / Community College'),
        ('cte_trade', 'CTE / Trade School'),
        ('apprenticeship', 'Apprenticeship'),
        ('military', 'Military'),
        ('workforce', 'Workforce / Employed'),
        ('gap_year', 'Gap Year'),
        ('unemployed', 'Unemployed / Seeking'),
        ('unknown', 'Unknown / No Contact'),
        ('other', 'Other'),
    ]

    STATUSES = [
        ('enrolled', 'Enrolled / Active'),
        ('persisting', 'Persisting'),
        ('on_track', 'On Track'),
        ('struggling', 'Struggling'),
        ('stopped_out', 'Stopped Out'),
        ('transferred', 'Transferred'),
        ('completed', 'Completed Credential'),
        ('unknown', 'Unknown'),
    ]

    @property
    def pathway_label(self):
        return dict(self.PATHWAYS).get(self.primary_pathway, self.primary_pathway)
