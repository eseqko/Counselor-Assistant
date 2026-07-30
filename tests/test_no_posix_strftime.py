"""Ban POSIX-only strftime directives that crash on Windows.

`%-d`, `%-m`, `%-I` (and friends) strip the leading zero on Linux/macOS but
raise ValueError on Windows, where this app is deployed. Every test here passes
on the CI Linux box while the page 500s in production — which is exactly how
"Today's Reminders" broke. Use the `smartdate` Jinja filter instead.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# The crash only happens when a POSIX-only directive reaches strftime. The same
# directive inside a smartdate() call is emulated and safe, so match strftime
# specifically rather than the bare directive.
POSIX_STRFTIME = re.compile(r"strftime\s*\(\s*['\"][^'\"]*%-[dmIHMjyU]")

SCAN_DIRS = ['app']
SUFFIXES = {'.py', '.html'}
# The one legitimate mention is the filter that exists to emulate these.
ALLOW = {'app/__init__.py'}


def _files():
    for d in SCAN_DIRS:
        for path in (ROOT / d).rglob('*'):
            if path.suffix in SUFFIXES and '__pycache__' not in path.parts:
                yield path


def test_no_posix_only_strftime_directives():
    offenders = []
    for path in _files():
        rel = path.relative_to(ROOT).as_posix()
        if rel in ALLOW:
            continue
        for i, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if POSIX_STRFTIME.search(line):
                offenders.append(f'{rel}:{i}  {line.strip()[:90]}')
    assert not offenders, (
        'POSIX-only strftime directives (crash on Windows — use the smartdate '
        'filter):\n' + '\n'.join(offenders))


@pytest.mark.parametrize('fmt,expected', [
    ('%b %-d, %Y', 'Aug 3, 2026'),
    ('%a %b %-d', 'Mon Aug 3'),
    ('%A, %b %-d', 'Monday, Aug 3'),
    ('%b %-d', 'Aug 3'),
])
def test_smartdate_strips_leading_zero_portably(app, fmt, expected):
    from datetime import date
    smartdate = app.jinja_env.filters['smartdate']
    assert smartdate(date(2026, 8, 3), fmt) == expected


def test_smartdate_handles_none_and_datetime(app):
    from datetime import datetime
    smartdate = app.jinja_env.filters['smartdate']
    assert smartdate(None, '%b %-d') == ''
    assert smartdate(datetime(2026, 8, 3, 14, 5), '%-I:%M %p') == '2:05 PM'


def test_todays_reminders_renders_with_single_digit_day(app):
    """The page that actually broke. A single-digit due date must format
    without a leading zero and without 500ing."""
    from datetime import date
    from app import db
    from app.models.note import Note
    from app.models.student import Student
    from app.models.user import User

    with app.app_context():
        uid = User.query.filter_by(username='demo').first().id
        sid = Student.query.filter_by(
            assigned_counselor_id=uid, status='active').first().id
        note = Note(student_id=sid, author_id=uid, note_type='academic',
                    title='Posix check', content='x', follow_up_needed=True,
                    follow_up_completed=False, follow_up_date=date(2026, 8, 3))
        db.session.add(note)
        db.session.commit()
        note_id = note.id

    client = app.test_client()
    client.get('/demo-login')
    r = client.get('/follow-ups/digest')
    assert r.status_code == 200
    assert b'Aug 3' in r.data

    with app.app_context():
        db.session.delete(db.session.get(Note, note_id))
        db.session.commit()
