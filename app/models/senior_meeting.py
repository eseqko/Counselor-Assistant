"""Senior / Post-Secondary 1:1 meetings.

A ``SeniorMeeting`` is one sit-down with one student: live notes, Solution-
Focused scaling numbers, answers to the ASCA / SFBT prompt bank, the student's
own next step with a date, and the counselor's follow-up. The post-secondary
checklist state lives per STUDENT in ``SeniorChecklistItem`` so a box ticked in
October stays ticked in March; each meeting only records which boxes it ticked.
School-wide deadlines (UC/CSU, FAFSA, Cal Grant...) are ``PostSecondaryDeadline``
rows, seeded from the content bank's defaults and editable each year.

Every row is counselor-owned (``counselor_id``) and student-linked; reads go
through owned_or_404 / caseload_student_or_404 like the rest of the app.
"""
import json
from datetime import datetime, timezone

from app import db


def _now():
    return datetime.now(timezone.utc)


class SeniorMeeting(db.Model):
    __tablename__ = 'senior_meetings'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    counselor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    meeting_date = db.Column(db.Date, nullable=False, index=True)
    meeting_kind = db.Column(db.String(10), default='first')      # first | followup
    status = db.Column(db.String(12), default='in_progress', index=True)  # in_progress | completed
    started_at = db.Column(db.DateTime, default=_now)
    completed_at = db.Column(db.DateTime)
    duration_minutes = db.Column(db.Integer)

    # Snapshot of the pathway discussed (mirrors CollegeCareerPlan.pathway).
    pathway = db.Column(db.String(30))

    # Solution-Focused scaling, 0-10.
    scale_plan = db.Column(db.Integer)        # "my plan for after high school is handled"
    scale_stress = db.Column(db.Integer)      # "how much is this weighing on you"
    scale_confidence = db.Column(db.Integer)  # "how sure are you you'll do the next step"

    notes = db.Column(db.Text)                # live free-form notes
    answers_json = db.Column(db.Text)         # {question_key: answer}
    checked_json = db.Column(db.Text)         # [checklist keys ticked during this meeting]

    # The student's own next small step, and the counselor's follow-up.
    next_step = db.Column(db.Text)
    next_step_due = db.Column(db.Date, index=True)
    next_step_done = db.Column(db.Boolean, default=False)
    follow_up_date = db.Column(db.Date)
    follow_up_notes = db.Column(db.Text)

    # How the meeting is logged in the counselor's notes timeline.
    note_type = db.Column(db.String(50), default='college_career')
    note_id = db.Column(db.Integer, db.ForeignKey('notes.id'))

    created_at = db.Column(db.DateTime, default=_now)
    updated_at = db.Column(db.DateTime, default=_now, onupdate=_now)

    student = db.relationship('Student', backref=db.backref(
        'senior_meetings', lazy='dynamic', order_by='SeniorMeeting.meeting_date.desc()'))
    counselor = db.relationship('User', backref='senior_meetings')
    note = db.relationship('Note', foreign_keys=[note_id])

    KINDS = [('first', 'First meeting'), ('followup', 'Follow-up')]

    @property
    def answers(self):
        try:
            data = json.loads(self.answers_json) if self.answers_json else {}
        except (TypeError, ValueError):
            data = {}
        return data if isinstance(data, dict) else {}

    @answers.setter
    def answers(self, value):
        self.answers_json = json.dumps(value or {}, default=str)

    @property
    def checked_keys(self):
        try:
            data = json.loads(self.checked_json) if self.checked_json else []
        except (TypeError, ValueError):
            data = []
        return [k for k in data if isinstance(k, str)] if isinstance(data, list) else []

    @checked_keys.setter
    def checked_keys(self, value):
        self.checked_json = json.dumps(sorted(set(value or [])))

    @property
    def is_open(self):
        return self.status != 'completed'

    @property
    def kind_label(self):
        return dict(self.KINDS).get(self.meeting_kind, self.meeting_kind or '')


class SeniorChecklistItem(db.Model):
    """One student's state for one checklist key (from senior_meeting_content)."""
    __tablename__ = 'senior_checklist_items'
    __table_args__ = (db.UniqueConstraint('student_id', 'key', name='uq_senior_checklist_student_key'),)

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    key = db.Column(db.String(60), nullable=False)
    done = db.Column(db.Boolean, default=False, nullable=False)
    done_at = db.Column(db.DateTime)
    meeting_id = db.Column(db.Integer, db.ForeignKey('senior_meetings.id'))  # where it was ticked
    note = db.Column(db.String(300))
    updated_at = db.Column(db.DateTime, default=_now, onupdate=_now)

    student = db.relationship('Student', backref=db.backref('senior_checklist_items', lazy='dynamic'))


class PostSecondaryDeadline(db.Model):
    """A school-wide post-secondary date (application, aid, testing, decision).

    Seeded from senior_meeting_content.DEADLINE_DEFAULTS and edited each year;
    ``verify`` flags a default whose exact date should be confirmed.
    """
    __tablename__ = 'post_secondary_deadlines'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(60), index=True)          # content-bank key when seeded, else None
    label = db.Column(db.String(200), nullable=False)
    date = db.Column(db.Date, nullable=False, index=True)
    pathways = db.Column(db.String(120), default='all')  # comma-separated pathway keys or 'all'
    category = db.Column(db.String(20), default='other')
    source = db.Column(db.String(200))
    note = db.Column(db.String(400))
    verify = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=_now)
    updated_at = db.Column(db.DateTime, default=_now, onupdate=_now)

    CATEGORIES = [
        ('application', 'Application'),
        ('financial_aid', 'Financial aid'),
        ('testing', 'Testing'),
        ('decision', 'Decision'),
        ('records', 'Records'),
        ('other', 'Other'),
    ]

    @property
    def pathway_list(self):
        return [p.strip() for p in (self.pathways or 'all').split(',') if p.strip()]

    def applies_to(self, pathway):
        paths = self.pathway_list
        return 'all' in paths or (pathway or 'undecided') in paths

    @property
    def category_label(self):
        return dict(self.CATEGORIES).get(self.category, self.category or '')
