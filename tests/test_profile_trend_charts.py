"""The trend sparklines at the top of the student profile.

They never drew. `_trends.html` builds its charts from an inline script that
runs as the body is parsed, guarded by `if (typeof Chart === 'undefined')
return;` — but nothing on the profile loaded Chart.js at that point. The only
include lived in `_elpac_scores.html`, which sits further down the document AND
is wrapped in `{% if elpac_records or student.is_el %}`, so for a non-EL student
the library never loaded at all. The guard swallowed it, the canvas kept its
reserved height, and the card looked like an empty box.
"""
import re

import pytest

from app import db
from app.models.grade import GradeRecord
from app.models.student import Student
from app.models.user import User

VENDOR = 'vendor/chart.js'
YEAR = '2025-2026'


@pytest.fixture
def profile_env(app):
    with app.app_context():
        User.query.filter_by(username='trend_me').delete(synchronize_session=False)
        Student.query.filter(Student.student_id_number.like('TRN-%')).delete(
            synchronize_session=False)
        db.session.commit()
        me = User(username='trend_me', display_name='Trend Me', role='counselor',
                  setup_completed=True)
        me.set_password('passw0rd123')
        db.session.add(me)
        db.session.commit()

        def student(num, el_status):
            s = Student(student_id_number=num, first_name='Ana', last_name='Reyes',
                        grade_level=12, status='active',
                        assigned_counselor_id=me.id, el_status=el_status)
            db.session.add(s)
            return s

        plain = student('TRN-1', 'EO')       # not EL: the broken case
        el = student('TRN-2', 'LTEL')
        db.session.commit()

        # Four quarters of finals, so the GPA trend has enough points to draw.
        for q, letter in ((1, 'B'), (2, 'B+'), (3, 'A-'), (4, 'A')):
            for course in ('Math Course 3 CP', 'English 12 CP'):
                db.session.add(GradeRecord(
                    student_id=plain.id, school_year=YEAR, quarter=q,
                    grade_type='final', course_name=course, course_number='X1',
                    period=1, teacher='Wong, J.', letter_grade=letter))
        db.session.commit()
        ids = dict(me=me.id, plain=plain.id, el=el.id)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(ids['me'])
        sess['_fresh'] = True
    yield client, ids

    with app.app_context():
        GradeRecord.query.filter(GradeRecord.student_id.in_(
            [ids['plain'], ids['el']])).delete(synchronize_session=False)
        Student.query.filter(Student.id.in_([ids['plain'], ids['el']])).delete(
            synchronize_session=False)
        User.query.filter_by(id=ids['me']).delete(synchronize_session=False)
        db.session.commit()


def test_a_non_el_students_profile_loads_chartjs(app, profile_env):
    """The exact regression: the only include was inside the EL-only partial,
    so this page had no charting library at all."""
    client, ids = profile_env
    html = client.get(f'/caseload/{ids["plain"]}').data.decode()
    assert VENDOR in html, 'profile renders canvases but never loads Chart.js'


def test_an_el_students_profile_loads_chartjs(app, profile_env):
    client, ids = profile_env
    assert VENDOR in client.get(f'/caseload/{ids["el"]}').data.decode()


def test_chartjs_is_loaded_exactly_once(app, profile_env):
    """Two copies would re-run chart-enhancements and re-register its plugins."""
    client, ids = profile_env
    for sid in (ids['plain'], ids['el']):
        html = client.get(f'/caseload/{sid}').data.decode()
        assert html.count(VENDOR) == 1, 'Chart.js included more than once'
        assert html.count('js/chart-enhancements.js') == 1


def test_the_library_loads_before_the_inline_chart_scripts(app, profile_env):
    """The scripts in the partials run while the body is parsed, so a library
    loaded after them is the same as no library — which is what happened."""
    client, ids = profile_env
    html = client.get(f'/caseload/{ids["plain"]}').data.decode()
    vendor_at = html.index(VENDOR)
    first_chart_call = html.index('new Chart(')
    assert vendor_at < first_chart_call, \
        'Chart.js is pulled in after the first inline chart script'


def test_the_gpa_canvas_is_rendered_when_there_are_enough_quarters(app, profile_env):
    client, ids = profile_env
    html = client.get(f'/caseload/{ids["plain"]}').data.decode()
    assert 'id="trend-gpa"' in html
    assert 'new Chart(document.getElementById(\'trend-gpa\')' in html
    assert 'Needs 2+ quarters of final grades' not in html


def test_a_student_with_no_grades_gets_the_explanation_not_an_empty_box(app, profile_env):
    """The empty state is correct behaviour and must not be mistaken for the
    bug — the difference is whether a message is shown at all."""
    client, ids = profile_env
    html = client.get(f'/caseload/{ids["el"]}').data.decode()
    assert 'Needs 2+ quarters of final grades' in html
    assert 'id="trend-gpa"' not in html


def test_the_elpac_partial_no_longer_ships_its_own_copy():
    """Kept as a unit so the duplicate cannot creep back via that partial."""
    from pathlib import Path
    p = (Path(__file__).resolve().parent.parent / 'app' / 'templates' /
         'caseload' / '_partials' / '_elpac_scores.html')
    text = p.read_text(encoding='utf-8')
    assert 'new Chart(' in text, 'partial no longer draws a chart at all'
    assert VENDOR not in text
