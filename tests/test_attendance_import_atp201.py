"""Importing the Synergy ATP201 attendance report.

The shape, verified against the counselor's real export: one row per student
per day-with-marks; columns Period 0..Period 10 with the attendance code in
the marked periods and blank meaning present/unscheduled; the student id in
'Sis Number' (there is no Perm ID column); dates tagged with the day's bell
schedule — "08/07/2026 (D2S)". The fixture here is synthetic in that exact
shape — the real report is never committed, because Sis Numbers and
demographics are education records.
"""
import io
from datetime import date

import pytest
from openpyxl import Workbook

from app import db
from app.models.attendance import AttendanceRecord
from app.models.student import Student
from app.models.user import User

# The real report's leading columns, in order (trailing parent-contact
# columns omitted — the importer never reads them).
ATP201_HEADER = [
    'School Name', 'School Year', 'Student Name', 'Legal Formatted Name',
    'Nick Name', 'Last Name Goes By', 'Ethnicity', 'Original Enter Date',
    'Final Withdrawal Date', 'Sis Number', 'Grade', 'Date',
    'Period 0', 'Period 1', 'Period 2', 'Period 3', 'Period 4', 'Period 5',
    'Period 6', 'Period 7', 'Period 8', 'Period 9', 'Period 10', 'Note',
]


def atp_row(sis, day, periods, grade=9):
    """One report row: ``periods`` maps period number -> code string."""
    cells = ['Jefferson High School', '2026-2027', '', '', '', '', 'White',
             '', '', sis, grade, day]
    for p in range(11):
        cells.append(periods.get(p, ''))
    cells.append('')
    return cells


def workbook(rows):
    wb = Workbook()
    ws = wb.active
    ws.append(ATP201_HEADER)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


@pytest.fixture
def atp_env(app):
    with app.app_context():
        User.query.filter_by(username='atp_me').delete(synchronize_session=False)
        Student.query.filter(Student.student_id_number.like('ATP-%')).delete(
            synchronize_session=False)
        Student.query.filter_by(student_id_number='9999999').delete(
            synchronize_session=False)
        db.session.commit()
        me = User(username='atp_me', display_name='ATP Me', role='counselor',
                  setup_completed=True)
        me.set_password('passw0rd123')
        db.session.add(me)
        db.session.commit()
        s = Student(student_id_number='ATP-1', first_name='Ana',
                    last_name='Reyes', grade_level=9, status='active',
                    assigned_counselor_id=me.id)
        db.session.add(s)
        db.session.commit()
        ids = dict(me=me.id, student=s.id)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(ids['me'])
        sess['_fresh'] = True
    yield client, ids

    with app.app_context():
        from app.models.import_log import ImportLog
        shadow_ids = [sid for (sid,) in db.session.query(Student.id).filter_by(
            student_id_number='9999999')]
        AttendanceRecord.query.filter(AttendanceRecord.student_id.in_(
            [ids['student']] + shadow_ids)).delete(synchronize_session=False)
        Student.query.filter(Student.id.in_(
            [ids['student']] + shadow_ids)).delete(synchronize_session=False)
        # The uploads wrote ImportLog rows keyed to this user; they must go
        # BEFORE the user, or a later flush tries to NULL the non-nullable FK
        # and poisons an unrelated test's session.
        ImportLog.query.filter_by(user_id=ids['me']).delete(
            synchronize_session=False)
        User.query.filter_by(id=ids['me']).delete(synchronize_session=False)
        db.session.commit()


def _upload(client, rows):
    return client.post('/data-import/attendance/upload',
                       data={'file': (workbook(rows), 'atp201.xlsx')},
                       content_type='multipart/form-data',
                       follow_redirects=True)


def test_atp201_imports_by_sis_number_with_annotated_dates(app, atp_env):
    """The two things that rejected the real report: no Perm ID column (the
    id lives in 'Sis Number') and bell-schedule tags on every date."""
    client, ids = atp_env
    _upload(client, [
        atp_row('ATP-1', '08/07/2026 (D2S)', {3: 'Unverified'}),
        atp_row('ATP-1', '08/18/2026 (MFonly)', {1: 'Ilness', 2: 'Ilness',
                                                 3: 'Ilness', 4: 'Ilness',
                                                 5: 'Ilness', 6: 'Ilness'}),
    ])
    with app.app_context():
        recs = AttendanceRecord.query.filter_by(student_id=ids['student']).all()
        # Live columns across the file are {1..6}; the padded Period 0 and
        # Period 7-10 columns must NOT become present rows (they made a fully
        # absent day read as under half the schedule).
        assert len(recs) == 12, 'one record per LIVE period column per listed day'
        assert {r.period for r in recs} == {1, 2, 3, 4, 5, 6}
        by_day = {}
        for r in recs:
            by_day.setdefault(r.date, {})[r.period] = (r.status, r.reason)
        d1 = by_day[date(2026, 8, 7)]
        assert d1[3] == ('absent', 'Unverified')
        assert d1[1] == ('present', ''), 'blank period cell means present'
        d2 = by_day[date(2026, 8, 18)]
        # "Ilness" is the SIS's own spelling; it must land as an excused
        # absence with the reason normalized.
        assert d2[1] == ('excused', 'Illness')


def test_atp201_code_spellings(app, atp_env):
    client, ids = atp_env
    _upload(client, [
        atp_row('ATP-1', '08/10/2026 (D2S)', {1: 'Unx.Tardy', 2: 'Activity',
                                              4: 'Office Ex'}),
    ])
    with app.app_context():
        by_period = {r.period: (r.status, r.reason) for r in
                     AttendanceRecord.query.filter_by(
                         student_id=ids['student'])}
        assert by_period[1] == ('tardy', 'Unexcused Tardy')
        assert by_period[2] == ('excused', 'Activity')
        assert by_period[4] == ('excused', 'Office Excused')


def test_unknown_sis_number_becomes_a_shadow_student(app, atp_env):
    """A schoolwide ATP201 includes students on no caseload — kept as
    anonymous shadow rows so the caseload-vs-school baseline exists."""
    client, ids = atp_env
    _upload(client, [atp_row('9999999', '08/07/2026 (D2S)', {2: 'Cut'})])
    with app.app_context():
        shadow = Student.query.filter_by(student_id_number='9999999').first()
        assert shadow is not None and shadow.is_shadow
        assert shadow.assigned_counselor_id is None
        assert AttendanceRecord.query.filter_by(
            student_id=shadow.id).count() == 1, 'only the live period column'


def test_reuploading_the_same_report_does_not_duplicate(app, atp_env):
    client, ids = atp_env
    rows = [atp_row('ATP-1', '08/07/2026 (D2S)', {3: 'Unverified'})]
    _upload(client, rows)
    _upload(client, rows)
    with app.app_context():
        assert AttendanceRecord.query.filter_by(
            student_id=ids['student']).count() == 1


def test_activity_rows_read_as_present_in_the_analysis(app, atp_env):
    """End to end into Attendance Insights: a day of Activity marks must not
    make the student an absentee — the district's own report excludes
    Activity from Total Absences."""
    client, ids = atp_env
    _upload(client, [
        atp_row('ATP-1', '08/07/2026 (D2S)',
                {p: 'Activity' for p in range(1, 7)}),
        atp_row('ATP-1', '08/10/2026 (D2S)', {3: 'Unverified'}),
    ])
    html = client.get('/reports/attendance-insights').data.decode()
    assert 'Ana Reyes' in html
    # Two school days, zero absent days (Activity is present-like, one cut
    # is a partial) -> satisfactory, not chronic.
    assert 'SATISFACTORY' in html.upper()


def test_the_upload_page_names_the_report(app, atp_env):
    client, _ = atp_env
    html = client.get('/data-import/attendance/upload').data.decode()
    assert 'ATP201' in html
    assert 'Sis Number' in html
    hub = client.get('/data-import/').data.decode()
    assert 'ATP201' in hub


def test_a_fully_absent_day_counts_absent_despite_column_padding(app, atp_env):
    """THE bug the real report exposed: ATP201 ships Period 0-10 columns but
    this school schedules five periods. Present-padding for dead columns made
    a fully absent day 5 of 11 slots (45%) — under the 50% threshold, so no
    day ever counted absent and every student read satisfactory."""
    client, ids = atp_env
    live = {p: 'Unverified' for p in (1, 2, 3, 4, 6)}       # the real bell schedule
    _upload(client, [
        atp_row('ATP-1', '08/07/2026 (D2S)', live),          # fully absent
        atp_row('ATP-1', '08/10/2026 (D2S)', {1: 'Unverified'}),  # one cut
        atp_row('ATP-1', '08/11/2026 (D2S)', {}),            # never listed blank...
    ][:2])
    html = client.get('/reports/attendance-insights').data.decode()
    assert 'Ana Reyes' in html
    assert '1 of 2' in html, 'the fully absent day must count as an absent day'
