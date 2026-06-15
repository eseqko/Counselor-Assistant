"""Persistent staff records — auto-created from the Staff Name column in grade
imports, then editable by the counselor (email, phone, room, title, notes, etc.).

The grade-derived directory still works without any manual entry; this model
just makes those records first-class so a counselor can keep contact info,
notes, and overrides alongside each teacher.
"""
from app import db
from datetime import datetime, timezone


class Staff(db.Model):
    __tablename__ = 'staff'

    id = db.Column(db.Integer, primary_key=True)

    # Identity. Name is the upsert key from grade imports (the Staff Name column
    # is what Synergy ships; there's no employee ID). Treated case-insensitively
    # on import via a normalized lookup but stored as-imported.
    name = db.Column(db.String(120), unique=True, nullable=False, index=True)

    # Editable contact + classification fields. All optional — auto-created
    # records start blank and a counselor fills in whatever's useful.
    email = db.Column(db.String(200))
    phone = db.Column(db.String(40))
    room = db.Column(db.String(40))
    title = db.Column(db.String(60))            # Teacher, Counselor, Admin, Aide, etc.
    department = db.Column(db.String(80))       # Overrides the subject-derived default
    notes = db.Column(db.Text)                  # Free-form ("speaks Spanish", "best contact: lunch")

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    TITLES = ['Teacher', 'Counselor', 'Administrator', 'Aide', 'Support Staff', 'Other']
