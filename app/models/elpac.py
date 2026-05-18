from app import db
from datetime import datetime, timezone


class ELPACScore(db.Model):
    """ELPAC (English Language Proficiency Assessments for California) test results.

    One row per test. Captures the Ellevation Education CSV export shape:
    domain scores (L/S/R/W), composite scores (Literacy, Oral, Comprehension),
    Overall, and ACPL. Raw scores intentionally omitted — counselors look at
    scale + level only.
    """
    __tablename__ = 'elpac_scores'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'),
                           nullable=False, index=True)

    # Test metadata (mirrors Ellevation columns)
    test_id = db.Column(db.String(50), index=True)   # Test ID # — for external reference
    test_purpose = db.Column(db.String(20))           # 'Summative' | 'Initial'
    test_date = db.Column(db.Date, index=True)
    test_grade_level = db.Column(db.Integer)
    test_cluster = db.Column(db.String(30))           # 'Grades 9-10', 'Grades K-2', etc.
    test_administrator = db.Column(db.String(200))
    school_year = db.Column(db.String(9))             # derived from test_date

    # Domain scores
    listening_scale = db.Column(db.Integer)
    listening_level = db.Column(db.Integer)
    speaking_scale = db.Column(db.Integer)
    speaking_level = db.Column(db.Integer)
    reading_scale = db.Column(db.Integer)
    reading_level = db.Column(db.Integer)
    writing_scale = db.Column(db.Integer)
    writing_level = db.Column(db.Integer)

    # Composite scores
    literacy_scale = db.Column(db.Integer)            # R + W
    literacy_level = db.Column(db.Integer)
    oral_scale = db.Column(db.Integer)                # L + S
    oral_level = db.Column(db.Integer)
    comprehension_scale = db.Column(db.Integer)       # L + R
    comprehension_level = db.Column(db.Integer)

    # Overall (Composite/Overall — the main reclassification score)
    overall_scale = db.Column(db.Integer)
    overall_level = db.Column(db.Integer, index=True)

    # ACPL (Alternate Composite Proficiency Level)
    acpl_scale = db.Column(db.Integer)
    acpl_level = db.Column(db.Integer)

    imported_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    imported_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    student = db.relationship('Student', backref=db.backref(
        'elpac_scores', lazy='dynamic', order_by='ELPACScore.test_date.desc()'
    ))
    imported_by = db.relationship('User', backref='elpac_imports')

    __table_args__ = (
        db.UniqueConstraint('student_id', 'test_date', 'test_purpose',
                            name='uq_elpac_student_date_purpose'),
    )

    TEST_PURPOSES = [
        ('Summative', 'Summative ELPAC'),
        ('Initial', 'Initial ELPAC'),
    ]
    OVERALL_LEVELS = [
        (1, '1 - Minimally Developed'),
        (2, '2 - Somewhat Developed'),
        (3, '3 - Moderately Developed'),
        (4, '4 - Well Developed'),
    ]
    DOMAIN_LEVELS = [
        (1, '1 - Beginning'),
        (2, '2 - Somewhat Developed'),
        (3, '3 - Well Developed'),
    ]
    TEST_CLUSTERS = [
        'Kindergarten', 'Grade 1', 'Grade 2',
        'Grades 3-5', 'Grades 6-8', 'Grades 9-10', 'Grades 11-12',
    ]

    @property
    def overall_level_label(self):
        return dict(self.OVERALL_LEVELS).get(self.overall_level, '')

    @property
    def is_rfep_eligible(self):
        return self.overall_level == 4
