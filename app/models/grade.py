from app import db
from datetime import datetime, timezone


class GradeRecord(db.Model):
    """Imported grade data for trend analysis, early warning, and course recommendations."""
    __tablename__ = 'grade_records'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)

    # Course info (4x4 schedule: 4 classes/quarter, 5 credits each)
    school_year = db.Column(db.String(9))   # e.g., "2025-2026"
    quarter = db.Column(db.Integer)          # 1, 2, 3, 4
    course_name = db.Column(db.String(200), nullable=False)
    course_number = db.Column(db.String(20))  # links to course catalog if available
    period = db.Column(db.Integer)            # 1-4
    teacher = db.Column(db.String(120), index=True)  # staff name from the grade export

    # Grade type: 'final' (quarter grades) or 'progress' (mid-quarter progress report)
    grade_type = db.Column(db.String(10), default='final')  # 'final' | 'progress'

    # Grade data
    letter_grade = db.Column(db.String(5), index=True)   # A, B, C, D, F, P, NP, I
    percent_grade = db.Column(db.Float)      # 0-100
    credits_earned = db.Column(db.Float, default=5.0)
    credits_attempted = db.Column(db.Float, default=5.0)
    is_semester = db.Column(db.Integer, default=1)  # 1=Sem1, 2=Sem2

    # Classification
    subject_area = db.Column(db.String(100))  # English, Math, Science, etc.
    is_ag = db.Column(db.Boolean, default=False)
    is_honors_ap = db.Column(db.Boolean, default=False)
    is_cte = db.Column(db.Boolean, default=False)

    # Metadata
    imported_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    imported_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Relationships
    student = db.relationship('Student', backref=db.backref(
        'grade_records', lazy='dynamic', order_by='GradeRecord.school_year.desc()'
    ))
    imported_by = db.relationship('User', backref='grade_imports')

    LETTER_GRADES = ['A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-',
                     'D+', 'D', 'D-', 'F', 'P', 'NP', 'I', 'W', 'NM']

    SUBJECT_AREAS = [
        'English', 'Math', 'Science', 'History/Social Science',
        'Fine Arts/LOTE', 'CTE', 'PE', 'Health', 'Electives',
    ]

    @property
    def is_passing(self):
        # 'NM' (No Mark) means the teacher didn't enter a grade — it carries no
        # pass/fail signal, same as a missing letter. Return None so it isn't
        # counted as either passing or failing in aggregates.
        if self.letter_grade == 'NM':
            return None
        if self.letter_grade:
            return self.letter_grade not in ('F', 'NP', 'I', 'W')
        if self.percent_grade is not None:
            return self.percent_grade >= 60
        return None

    @property
    def gpa_points(self):
        """Standard 4.0 scale."""
        grade_map = {
            'A+': 4.0, 'A': 4.0, 'A-': 3.7,
            'B+': 3.3, 'B': 3.0, 'B-': 2.7,
            'C+': 2.3, 'C': 2.0, 'C-': 1.7,
            'D+': 1.3, 'D': 1.0, 'D-': 0.7,
            'F': 0.0,
        }
        return grade_map.get(self.letter_grade)
