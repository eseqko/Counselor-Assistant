from app import db
from datetime import datetime, timezone


class CalendarEvent(db.Model):
    __tablename__ = 'calendar_events'

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    location = db.Column(db.String(200))

    # Timing
    start_datetime = db.Column(db.DateTime, nullable=False)
    end_datetime = db.Column(db.DateTime, nullable=False)
    all_day = db.Column(db.Boolean, default=False)

    # Categorization
    event_type = db.Column(db.String(50), default='appointment')
    # appointment, meeting, classroom_lesson, group_session, parent_conference,
    # team_meeting, professional_dev, deadline, personal, other
    color = db.Column(db.String(7), default='#4A90D9')

    # Related student (optional)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'))

    # Recurrence
    is_recurring = db.Column(db.Boolean, default=False)
    recurrence_rule = db.Column(db.String(200))  # RRULE format
    recurrence_end = db.Column(db.Date)

    # Reminders
    reminder_minutes = db.Column(db.Integer, default=15)

    # Status
    status = db.Column(db.String(20), default='scheduled')  # scheduled, completed, cancelled
    completed_notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    student = db.relationship('Student', backref='calendar_events')

    EVENT_TYPES = [
        ('appointment', 'Appointment'),
        ('meeting', 'Meeting'),
        ('classroom_lesson', 'Classroom Lesson'),
        ('group_session', 'Group Session'),
        ('parent_conference', 'Parent Conference'),
        ('team_meeting', 'Team Meeting'),
        ('professional_dev', 'Professional Development'),
        ('deadline', 'Deadline'),
        ('follow_up', 'Follow-Up'),
        ('personal', 'Personal'),
        ('other', 'Other'),
    ]

    EVENT_COLORS = {
        'appointment': '#4A90D9',
        'meeting': '#7B68EE',
        'classroom_lesson': '#2ECC71',
        'group_session': '#F39C12',
        'parent_conference': '#E74C3C',
        'team_meeting': '#9B59B6',
        'professional_dev': '#1ABC9C',
        'deadline': '#E67E22',
        'follow_up': '#E91E63',
        'personal': '#95A5A6',
        'other': '#34495E',
    }
