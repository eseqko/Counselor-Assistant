from datetime import datetime, timezone
from app import db


class AcademicPlan(db.Model):
    __tablename__ = 'academic_plans'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'),
                           unique=True, nullable=False, index=True)
    # JSON: {"9": {"term1": [{slot, course_number, course_title, credits, source, ...}], "term2": [...]}, ...}
    plan_json = db.Column(db.Text)
    projected_total_credits = db.Column(db.Float, default=0)
    projected_ag_met = db.Column(db.Integer, default=0)
    projected_risk = db.Column(db.String(20))
    is_locked = db.Column(db.Boolean, default=False)
    locked_at = db.Column(db.DateTime)
    counselor_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    student = db.relationship('Student', backref=db.backref('academic_plan', uselist=False))
    counselor = db.relationship('User')
