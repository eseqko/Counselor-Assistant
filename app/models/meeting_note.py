"""Meeting Notes model -- supports multi-student linking via @mentions."""
from app import db
from datetime import datetime, timezone


# Many-to-many: meeting notes <-> students
meeting_note_students = db.Table(
    'meeting_note_students',
    db.Column('meeting_note_id', db.Integer, db.ForeignKey('meeting_notes.id'), primary_key=True),
    db.Column('student_id', db.Integer, db.ForeignKey('students.id'), primary_key=True)
)


class MeetingNote(db.Model):
    __tablename__ = 'meeting_notes'

    id = db.Column(db.Integer, primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(300), nullable=False)
    content = db.Column(db.Text, nullable=False)           # Raw text with @[Name](id) markers
    content_html = db.Column(db.Text)                       # Rendered HTML with linked chips
    meeting_type = db.Column(db.String(50), default='general')
    meeting_date = db.Column(db.Date, nullable=False)
    duration_minutes = db.Column(db.Integer)
    location = db.Column(db.String(200))
    attendees = db.Column(db.Text)                          # Free-text: other people present
    action_items = db.Column(db.Text)                       # Follow-up actions from the meeting
    is_confidential = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    author = db.relationship('User', backref='meeting_notes')
    students = db.relationship('Student', secondary=meeting_note_students,
                               backref=db.backref('meeting_notes', lazy='dynamic'),
                               lazy='joined')
