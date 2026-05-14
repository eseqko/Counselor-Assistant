"""Per-request data-state flags for progressive disclosure.

Single source of truth for "what data does this user actually have?"
Used by the inject_app_state context processor to gate sidebar items,
dashboard sections, and AI buttons.

Each check is a single LIMIT 1 against an indexed FK column, so the
total per-page DB cost is sub-millisecond on SQLite.
"""
import time
from flask import g
from app import db
from app.models.student import Student
from app.models.transcript import TranscriptRecord
from app.models.grade import GradeRecord
from app.models.attendance import AttendanceRecord
from app.models.activity import Activity


# Module-level TTL cache for Ollama availability. Probing on every page
# load would add 50-200ms (or up to 3s on connection failure) of latency
# per request; once-per-minute is enough to feel responsive.
_AI_CACHE = {'ts': 0.0, 'available': False}
_AI_TTL = 60  # seconds


def _ai_available():
    now = time.time()
    if now - _AI_CACHE['ts'] > _AI_TTL:
        from app.utils import ollama_client
        _AI_CACHE['available'] = ollama_client.is_available()
        _AI_CACHE['ts'] = now
    return _AI_CACHE['available']


def invalidate_ai_cache():
    """Force the next compute_state() call to re-probe Ollama. Hook this
    from the settings page after the user updates Ollama base URL/model.
    """
    _AI_CACHE['ts'] = 0.0


def compute_state(user):
    """Return a dict of data-state booleans for the current user.

    Cached on flask.g so multiple template references in one request
    share the same result.
    """
    if hasattr(g, '_app_state'):
        return g._app_state

    student_ids_select = db.select(Student.id).where(
        Student.assigned_counselor_id == user.id
    )

    state = {
        'has_students': db.session.query(Student.id).filter_by(
            assigned_counselor_id=user.id
        ).first() is not None,
        'has_transcripts': db.session.query(TranscriptRecord.id).filter(
            TranscriptRecord.student_id.in_(student_ids_select)
        ).first() is not None,
        'has_grades': db.session.query(GradeRecord.id).filter(
            GradeRecord.student_id.in_(student_ids_select)
        ).first() is not None,
        'has_attendance': db.session.query(AttendanceRecord.id).filter(
            AttendanceRecord.student_id.in_(student_ids_select)
        ).first() is not None,
        'has_activities': db.session.query(Activity.id).filter_by(
            counselor_id=user.id
        ).first() is not None,
        'has_ai': _ai_available(),
    }
    g._app_state = state
    return state
