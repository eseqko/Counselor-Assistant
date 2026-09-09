"""The Attendance Insights report: scoping, filters, baseline, rendering.

The analysis math itself is pinned in test_attendance_analysis.py; this file
covers the route — who is counted, who is never shown, and that the page says
what the data supports.
"""
from datetime import date, timedelta

import pytest

from app import db
from app.models.attendance import AttendanceRecord
from app.models.student import Student
from app.models.user import User


# The fixture's 20 school days sit 12-40 days back, but the report's default
# window is the school year (Aug 1), which clips them by an amount that depends
# on today's date — through mid-August they are not in it at all and the page
# shows its empty-state prompt instead. Assertions that need the fixture
# in-window ask for the 90-day one (see test_tier_filter_narrows_the_watchlist).
FULL_WINDOW = '/reports/attendance-insights?window=90'


def _school_days(start, n):
    out, cur = [], start
    while len(out) < n:
        if cur.weekday() < 5:
            out.append(cur)
        cur += timedelta(days=1)
    return out


@pytest.fixture
def att_env(app):
    """Two counselors, a shadow student for the schoolwide baseline, and one
    caseload student with a heavy Friday pattern."""
    with app.app_context():
        User.query.filter(User.username.in_(['att_me', 'att_other'])).delete(
            synchronize_session=False)
        Student.query.filter(Student.student_id_number.like('ATT-%')).delete(
            synchronize_session=False)
        db.session.commit()

        me = User(username='att_me', display_name='Att Me', role='counselor',
                  setup_completed=True)
        me.set_password('passw0rd123')
        other = User(username='att_other', display_name='Att Other',
                     role='counselor', setup_completed=True)
        other.set_password('passw0rd123')
        db.session.add_all([me, other])
        db.session.commit()

        def student(num, first, counselor, shadow=False, sample=False):
            s = Student(student_id_number=num, first_name=first,
                        last_name='Test', grade_level=11, status='active',
                        assigned_counselor_id=counselor, is_shadow=shadow,
                        is_sample=sample)
            db.session.add(s)
            return s

        fri = student('ATT-1', 'Friday', me.id)      # Mon/Fri pattern + severe
        ok = student('ATT-2', 'Okay', me.id)         # clean attendance
        ghost = student('ATT-3', 'Ghost', me.id)     # no attendance rows
        theirs = student('ATT-4', 'Their', other.id)
        shadow = student('ATT-5', 'Shadow', None, shadow=True)
        sample = student('ATT-6', 'Sample', me.id, sample=True)
        db.session.commit()

        days = _school_days(date.today() - timedelta(days=40), 20)
        fridays = {d for d in days if d.weekday() == 4}
        first_monday = next(d for d in days if d.weekday() == 0)

        def add(sid, day, status):
            db.session.add(AttendanceRecord(
                student_id=sid, date=day, status=status, period=None))

        for day in days:
            add(fri.id, day,
                'absent' if (day in fridays or day == first_monday) else 'present')
            add(ok.id, day, 'present')
            add(theirs.id, day, 'present')
            # The shadow student is chronically absent: schoolwide baseline
            # should read worse than the caseload's own numbers.
            add(shadow.id, day, 'absent' if day.weekday() in (1, 3) else 'present')
        db.session.commit()

        ids = dict(me=me.id, other=other.id, fri=fri.id, ok=ok.id,
                   ghost=ghost.id, theirs=theirs.id, shadow=shadow.id,
                   sample=sample.id)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(ids['me'])
        sess['_fresh'] = True
    yield client, ids

    with app.app_context():
        AttendanceRecord.query.filter(AttendanceRecord.student_id.in_(
            list(ids.values()))).delete(synchronize_session=False)
        Student.query.filter(Student.student_id_number.like('ATT-%')).delete(
            synchronize_session=False)
        User.query.filter(User.id.in_([ids['me'], ids['other']])).delete(
            synchronize_session=False)
        db.session.commit()


def test_report_renders_with_the_watchlist(app, att_env):
    client, ids = att_env
    r = client.get(FULL_WINDOW)
    assert r.status_code == 200
    html = r.data.decode()
    assert 'Watch-List' in html
    assert 'Friday Test' in html
    assert 'Severe' in html


def test_patterns_appear_when_the_window_covers_them(app, att_env):
    """The fixture spans ~40 calendar days; early in a school year the default
    Aug-1 window holds too few of them for the 5-absence Mon/Fri minimum, so
    the pattern assertions use the 90-day window — as a counselor would."""
    client, ids = att_env
    html = client.get('/reports/attendance-insights?window=90').data.decode()
    assert 'Friday Test' in html
    assert 'Mon/Fri' in html
    assert 'Monday / Friday Pattern' in html


def test_never_shows_another_counselors_or_shadow_or_sample_students(app, att_env):
    client, ids = att_env
    html = client.get(FULL_WINDOW).data.decode()
    assert 'Their Test' not in html, "another counselor's student leaked"
    assert 'Shadow Test' not in html, 'shadow students are aggregate-only'
    assert 'Sample Test' not in html


def test_students_without_data_are_listed_not_invented(app, att_env):
    client, ids = att_env
    html = client.get(FULL_WINDOW).data.decode()
    assert 'Ghost Test' in html
    assert 'No attendance data' in html


def test_schoolwide_baseline_includes_shadow_attendance(app, att_env):
    """The chronically-absent shadow student must drag the schoolwide mean
    below the caseload's own — that's the whole point of shadow rows."""
    client, ids = att_env
    html = client.get(FULL_WINDOW).data.decode()
    assert 'Schoolwide' in html
    assert 'pp vs school' in html


def test_tier_filter_narrows_the_watchlist(app, att_env):
    """Uses the 90-day window for the same reason as
    test_patterns_appear_when_the_window_covers_them: the fixture's 20 school
    days sit 12-40 days back, and the default school-year window (Aug 1) clips
    them by an amount that depends on today's date. Friday Test's 5-of-20
    absent days (25%, severe) read as no data at all through mid-August and as
    2-of-14 (chronic) in early September, so a severe filter dropped the row
    on most days of the year. The 90-day window always holds the whole
    fixture, which pins the tier."""
    client, ids = att_env
    html = client.get(FULL_WINDOW + '&tier=severe').data.decode()
    assert 'Friday Test' in html
    assert 'Okay Test' not in html, 'satisfactory student survived a severe filter'


def test_declining_filter(app, att_env):
    client, ids = att_env
    r = client.get('/reports/attendance-insights?declining=1')
    assert r.status_code == 200


def test_empty_window_shows_the_import_prompt(app, att_env):
    client, ids = att_env
    # 30-day window can still include our fixture (created within 40 days),
    # so probe with a counselor who has no attendance at all instead.
    with client.session_transaction() as sess:
        sess['_user_id'] = str(ids['other'])
    with app.app_context():
        AttendanceRecord.query.filter_by(student_id=ids['theirs']).delete(
            synchronize_session=False)
        db.session.commit()
    html = client.get('/reports/attendance-insights').data.decode()
    assert 'No attendance records in this window' in html
    assert 'Import Attendance' in html


def test_report_is_listed_on_the_reports_index(app, att_env):
    client, ids = att_env
    html = client.get('/reports/').data.decode()
    assert 'Attendance Insights' in html
    assert '/reports/attendance-insights' in html


def test_the_method_footnote_names_the_thresholds(app, att_env):
    """The tier ladder must be stated on the page, because other pages count
    raw records and WILL read differently on period-level data."""
    client, ids = att_env
    html = client.get(FULL_WINDOW).data.decode()
    for phrase in ('chronic 10', 'severe', 'half', 'Early Warning'):
        assert phrase in html, f'method footnote lost: {phrase}'


# ── the profile's attendance detail card ──

def test_profile_shows_the_attendance_detail(app, att_env):
    client, ids = att_env
    html = client.get(f'/caseload/{ids["fri"]}').data.decode()
    assert 'Attendance This Year' in html
    assert 'ABSENCE STREAK' in html
    # The heatmap grid and its legend render.
    assert 'Unexcused absence' in html
    assert 'Same math as' in html


def test_profile_attendance_card_absent_when_no_data(app, att_env):
    client, ids = att_env
    html = client.get(f'/caseload/{ids["ghost"]}').data.decode()
    assert 'Attendance This Year' not in html


def test_profile_enrolled_days_come_from_the_school_calendar(app, att_env):
    """A student marked on only some days must still be measured against the
    school's day count, not their own listed days."""
    client, ids = att_env
    today = date.today()
    start = (date(today.year - 1, 8, 1) if today.month < 8
             else date(today.year, 8, 1))
    with app.app_context():
        # Strip Friday Test down to ONLY absent-day rows (exception style).
        AttendanceRecord.query.filter_by(
            student_id=ids['fri'], status='present').delete(
            synchronize_session=False)
        db.session.commit()
        n_days = db.session.query(AttendanceRecord.date).filter(
            AttendanceRecord.date >= start).distinct().count()
        n_marked = db.session.query(AttendanceRecord.date).filter(
            AttendanceRecord.student_id == ids['fri'],
            AttendanceRecord.date >= start).distinct().count()
    assert n_marked < n_days, 'fixture must leave the student under-marked'
    html = client.get(f'/caseload/{ids["fri"]}').data.decode()
    assert f'of {n_days}' in html, (
        'enrolled days must be the school calendar, not the marked days')
