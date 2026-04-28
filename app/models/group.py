from app import db
from datetime import datetime, timezone


class CounselingGroup(db.Model):
    """Small-group counseling sessions with rosters and outcomes."""
    __tablename__ = 'counseling_groups'

    id = db.Column(db.Integer, primary_key=True)
    counselor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    name = db.Column(db.String(200), nullable=False)
    group_type = db.Column(db.String(50))
    asca_domain = db.Column(db.String(50))
    description = db.Column(db.Text)

    schedule = db.Column(db.String(200))
    location = db.Column(db.String(200))

    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    status = db.Column(db.String(20), default='active', index=True)

    pre_assessment = db.Column(db.Text)
    post_assessment = db.Column(db.Text)
    outcome_summary = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    counselor = db.relationship('User', backref='counseling_groups')
    members = db.relationship('GroupMember', backref='group',
                              cascade='all, delete-orphan')
    sessions = db.relationship('GroupSession', backref='group',
                               cascade='all, delete-orphan',
                               order_by='GroupSession.session_date')

    GROUP_TYPES = [
        ('grief', 'Grief / Loss'),
        ('anxiety', 'Anxiety / Stress'),
        ('social_skills', 'Social Skills'),
        ('anger', 'Anger Management'),
        ('study_skills', 'Study Skills'),
        ('college_career', 'College & Career'),
        ('divorce_family', 'Divorce / Family Change'),
        ('substance', 'Substance Use Education'),
        ('newcomer', 'Newcomer / EL'),
        ('lgbtq', 'LGBTQ+ Support'),
        ('grade_transition', 'Grade Transition'),
        ('peer_mediation', 'Peer Mediation'),
        ('other', 'Other'),
    ]

    STATUSES = [
        ('planning', 'Planning'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]


class GroupMember(db.Model):
    __tablename__ = 'group_members'

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('counseling_groups.id'), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)

    consent_status = db.Column(db.String(20), default='pending')  # pending, received, declined
    consent_date = db.Column(db.Date)
    pre_score = db.Column(db.String(50))
    post_score = db.Column(db.String(50))
    notes = db.Column(db.Text)

    enrolled_date = db.Column(db.Date, default=lambda: datetime.now(timezone.utc).date())
    exited_date = db.Column(db.Date)
    exit_reason = db.Column(db.String(100))

    student = db.relationship('Student', backref=db.backref('group_memberships', lazy='dynamic'))


class GroupSession(db.Model):
    __tablename__ = 'group_sessions'

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('counseling_groups.id'), nullable=False, index=True)

    session_date = db.Column(db.Date, nullable=False)
    session_number = db.Column(db.Integer)
    topic = db.Column(db.String(300))
    notes = db.Column(db.Text)
    duration_minutes = db.Column(db.Integer)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    attendance = db.relationship('GroupAttendance', backref='session',
                                 cascade='all, delete-orphan')


class GroupAttendance(db.Model):
    __tablename__ = 'group_attendance'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('group_sessions.id'), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)

    status = db.Column(db.String(20), default='present')  # present, absent, late, excused
    notes = db.Column(db.String(300))

    student = db.relationship('Student')

    STATUSES = [
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
        ('excused', 'Excused'),
    ]
