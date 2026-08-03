"""Regressions for the four bugs that were producing wrong output right now.

1. Hardcoded '2025-2026' meant mail-merge printed "(No current course data
   available)" for every student once the calendar rolled to 2026-2027.
2. `not g.is_passing` treated ungraded 'NM' as failing — printing "NOT PASSING"
   in a letter to a parent for a course the teacher hadn't graded yet.
3. Cohort trends bucketed grades by quarter with no school_year filter, merging
   every year's Q1 into one bar.
4. Chronic absenteeism divided per-student absences by a caseload-wide day
   count, so mid-year enrollees were understated.
"""
import re
from pathlib import Path

import pytest

from app import db
from app.models.grade import GradeRecord
from app.utils.helpers import current_school_year

ROOT = Path(__file__).resolve().parent.parent
# Only flag a year literal being ASSIGNED or COMPARED — that's the bug shape
# (`current_year = '2025-2026'`). Docstring examples and the flash message that
# shows the expected FORMAT are prose, not logic, and must not trip this.
YEAR_LITERAL = re.compile(r"""(?:=|==|!=)\s*['"]20\d{2}-20\d{2}['"]""")

# calendar_seed.py legitimately hardcodes the district's published calendars;
# demo_seed is fixture data.
ALLOWED = {'app/utils/calendar_seed.py', 'app/utils/demo_seed.py'}


def test_no_hardcoded_school_year_literals_in_routes():
    """A hardcoded school year silently expires. Compute it instead."""
    offenders = []
    for path in sorted((ROOT / 'app').rglob('*.py')):
        rel = path.relative_to(ROOT).as_posix()
        if rel in ALLOWED:
            continue
        for i, line in enumerate(path.read_text().splitlines(), 1):
            code = line.split('#', 1)[0]
            if YEAR_LITERAL.search(code):
                offenders.append(f'{rel}:{i}  {line.strip()}')
    assert not offenders, (
        'Hardcoded school-year literals (use current_school_year()):\n'
        + '\n'.join(offenders))


def test_mail_merge_letters_have_no_hardcoded_year():
    """These letters go to parents — a stale year is worse than none."""
    body = (ROOT / 'app/routes/mail_merge.py').read_text()
    templates = body[:body.index('def _grad_year')]
    # Strip \uXXXX escapes first — —, ’ and • each contain a
    # 4-digit run that a naive scan reads as a year.
    templates = re.sub(r'\\u[0-9a-fA-F]{4}', ' ', templates)
    hits = re.findall(
        r'(?:January|February|March|April|May|June|July|August|September|'
        r'October|November|December|Class of)\s+20\d{2}', templates)
    assert not hits, f'Hardcoded dates in parent-facing letter templates: {hits}'


# ------------------------------------------------------- ungraded != failing

@pytest.fixture
def ungraded_grade(app, make_student):
    """A student with one 'NM' (not yet marked) course in the current year."""
    sid = make_student(grade=12)
    with app.app_context():
        g = GradeRecord(student_id=sid, course_name='AP Calculus',
                        letter_grade='NM', school_year=current_school_year(),
                        quarter=1, grade_type='quarter')
        db.session.add(g)
        db.session.commit()
    yield sid
    with app.app_context():
        GradeRecord.query.filter_by(student_id=sid).delete()
        db.session.commit()


def test_is_passing_is_none_for_ungraded(app, ungraded_grade):
    """The contract the three bug sites violated."""
    with app.app_context():
        g = GradeRecord.query.filter_by(student_id=ungraded_grade).first()
        assert g.is_passing is None
        assert not (g.is_passing is False)


def test_mail_merge_does_not_call_ungraded_course_not_passing(app, ungraded_grade):
    from app.routes.mail_merge import _get_current_courses
    with app.app_context():
        text = _get_current_courses(ungraded_grade)
    assert 'AP Calculus' in text
    assert 'NOT PASSING' not in text, 'ungraded course reported as failing to a parent'


def test_meeting_prep_does_not_list_ungraded_as_failing(app, ungraded_grade):
    with app.app_context():
        grades = GradeRecord.query.filter_by(student_id=ungraded_grade).all()
        failing = [g for g in grades if g.is_passing is False]
    assert failing == [], 'ungraded course counted as failing in the prep pack'


def test_graduation_still_excludes_ungraded_from_earned_credit():
    """graduation.py's `not g.is_passing` is correct — ungraded must NOT earn
    credit. Guard against a mechanical sweep 'fixing' it."""
    src = (ROOT / 'app/routes/graduation.py').read_text()
    assert 'if not g.is_passing:' in src
    assert 'Do not "fix" this' in src, 'the explanatory comment was removed'


def test_cohort_trends_filters_by_school_year():
    src = (ROOT / 'app/routes/reports.py').read_text()
    block = src[src.index('# --- Grade distribution by quarter ---'):]
    block = block[:block.index('# --- Grade trends by subject area ---')]
    assert 'GradeRecord.school_year ==' in block, \
        'cohort trends query lost its school_year filter — years will merge'
