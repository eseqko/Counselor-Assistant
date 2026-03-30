"""Availability slots and booking records for appointment scheduling."""
from app import db
from datetime import datetime, timezone


class AvailabilitySlot(db.Model):
    """Recurring weekly availability windows set by the counselor."""
    __tablename__ = 'availability_slots'

    id = db.Column(db.Integer, primary_key=True)
    counselor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Mon, 1=Tue ... 6=Sun
    start_time = db.Column(db.String(5), nullable=False)  # HH:MM (24h)
    end_time = db.Column(db.String(5), nullable=False)    # HH:MM (24h)
    slot_duration = db.Column(db.Integer, default=30)     # minutes per booking slot
    is_active = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    counselor = db.relationship('User', backref='availability_slots')

    DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday',
                 'Saturday', 'Sunday']

    def to_dict(self):
        return {
            'id': self.id,
            'day_of_week': self.day_of_week,
            'day_name': self.DAY_NAMES[self.day_of_week],
            'start_time': self.start_time,
            'end_time': self.end_time,
            'slot_duration': self.slot_duration,
            'is_active': self.is_active,
        }


class Booking(db.Model):
    """A booked appointment from the public scheduling page."""
    __tablename__ = 'bookings'

    id = db.Column(db.Integer, primary_key=True)
    counselor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'))

    # Booker info (parent/guardian or student)
    booker_name = db.Column(db.String(200), nullable=False)
    booker_email = db.Column(db.String(200))
    booker_phone = db.Column(db.String(30))
    booker_relationship = db.Column(db.String(50))  # parent, student, teacher

    # Student reference (name if not in system)
    student_name = db.Column(db.String(200))

    # Appointment details
    meeting_type = db.Column(db.String(50), default='general')
    # general, academic, college, personal, parent_conference, schedule_change
    notes = db.Column(db.Text)
    appointment_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.String(5), nullable=False)  # HH:MM
    end_time = db.Column(db.String(5), nullable=False)    # HH:MM

    # Status
    status = db.Column(db.String(20), default='confirmed')  # confirmed, cancelled, completed
    google_event_id = db.Column(db.String(200))  # linked Google Calendar event

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    counselor = db.relationship('User', backref='bookings')
    student = db.relationship('Student', backref='bookings')

    MEETING_TYPES = [
        ('general', 'General Check-In'),
        ('academic', 'Academic Concern'),
        ('college', 'College/Career Planning'),
        ('personal', 'Personal/Social Support'),
        ('parent_conference', 'Parent Conference'),
        ('schedule_change', 'Schedule Change Request'),
    ]

    def to_dict(self):
        return {
            'id': self.id,
            'booker_name': self.booker_name,
            'booker_email': self.booker_email,
            'booker_phone': self.booker_phone,
            'booker_relationship': self.booker_relationship,
            'student_name': self.student_name,
            'meeting_type': self.meeting_type,
            'meeting_type_label': dict(self.MEETING_TYPES).get(self.meeting_type, self.meeting_type),
            'notes': self.notes,
            'appointment_date': self.appointment_date.isoformat() if self.appointment_date else None,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'status': self.status,
            'google_event_id': self.google_event_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
