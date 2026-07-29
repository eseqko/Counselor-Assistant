"""Current class schedule — one row per course a student is enrolled in.

Deliberately SEPARATE from GradeRecord even though the columns overlap almost
exactly. A schedule row is a GradeRecord before the grade exists, and putting
gradeless rows in that table would feed straight into GPA, "failing" counts and
earned-credit math — the same conflation that produced several live bugs
(ungraded 'NM' being reported as NOT PASSING to parents, etc.). Same column
NAMES so the existing by_teacher / by_course analytics helpers port over
unchanged; different table so grade logic can never see these.

Source of truth is the SIS. Two importers feed it (Synergy U-SCH100 Excel
export, and the printed first-day PDF schedule) via app/utils/schedule_parser.py.
"""
from datetime import datetime, timezone

from app import db


class ScheduleEntry(db.Model):
    __tablename__ = 'schedule_entries'
    __table_args__ = (
        # The hot paths: "this student's schedule" and the cohort/trend
        # roll-ups that group a caseload by period or by teacher.
        db.Index('ix_schedule_entries_student_year', 'student_id', 'school_year'),
        db.Index('ix_schedule_entries_year_period', 'school_year', 'period'),
        db.Index('ix_schedule_entries_year_teacher', 'school_year', 'teacher_name'),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'),
                           nullable=False, index=True)

    school_year = db.Column(db.String(9), nullable=False)   # "2026-2027"
    # Canonical term. Synergy sends Q1-Q4 plus 'YR' for year-long rows; the
    # printed PDF writes 'FALL & SPRING' for the same thing. Normalized on the
    # way in so both importers agree — see schedule_parser.normalize_term.
    term = db.Column(db.String(12), nullable=False)         # Q1|Q2|Q3|Q4|YR
    period = db.Column(db.Integer, index=True)

    course_number = db.Column(db.String(20), index=True)    # Synergy "Course ID"
    course_title = db.Column(db.String(200))
    section_id = db.Column(db.String(30))    # "6-011 12th" — encodes advisory grade
    teacher_name = db.Column(db.String(120), index=True)    # "Sachs, S."
    room = db.Column(db.String(30))
    start_date = db.Column(db.Date)          # Synergy "Enter Date"

    # Resolved from the Course catalog by course_number, or confirmed by the
    # counselor on the import preview. None means "still needs a value" and is
    # surfaced in a fix-up list rather than silently counted as zero.
    credits = db.Column(db.Float)

    # Advisory/homeroom rows drive group creation; non-class rows (a "Vice
    # Principal" assignment sits in period 7 with no room) are kept for the
    # record but excluded from credits and from teaching-load counts.
    is_advisory = db.Column(db.Boolean, default=False)
    is_non_class = db.Column(db.Boolean, default=False)

    source = db.Column(db.String(20), default='excel')      # excel | pdf | manual
    imported_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    imported_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    student = db.relationship('Student', backref=db.backref(
        'schedule_entries', lazy='dynamic', cascade='all, delete-orphan'))

    # Terms that make up a full year, in display order.
    TERM_ORDER = ['YR', 'Q1', 'Q2', 'Q3', 'Q4']

    def __repr__(self):
        return (f'<ScheduleEntry {self.student_id} {self.school_year} '
                f'{self.term} P{self.period} {self.course_title}>')

    @property
    def counts_for_credit(self):
        """Whether this row should contribute to in-progress credit totals."""
        return not self.is_non_class and not self.is_advisory

    @property
    def teacher_display(self):
        """'Sachs, S.' -> 'S. Sachs' for prose contexts."""
        if not self.teacher_name or ',' not in self.teacher_name:
            return self.teacher_name or ''
        last, first = [p.strip() for p in self.teacher_name.split(',', 1)]
        return f'{first} {last}'.strip()
