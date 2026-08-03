"""Schedule import: matching, preview, commit, replace-on-reimport, ownership.

The rule this file protects: a schedule attached to the WRONG student is worse
than one that's missing, so an unmatched row is reported, never guessed.
"""
import io
import os
from pathlib import Path

import pytest
from openpyxl import Workbook

from app import db
from app.models.course import Course
from app.models.schedule import ScheduleEntry
from app.models.staff import Staff
from app.models.student import Student
from app.models.user import User

FIXTURES = Path(__file__).parent / 'fixtures'
SAMPLE_XLS = FIXTURES / 'schedule_sample.xls'
SAMPLE_PDF = FIXTURES / 'schedule_sample.pdf'

HEADER = ['Perm ID', 'Student Name', 'Grade', 'Course ID', 'Course Title',
          'Section ID', 'Term Code', 'Begin Period', 'Staff Name', 'Room Name',
          'FullYear']

ROWS = [
    ('25248', 'Fashion Design CP [S1]', '1-019', 'Q1', 1, 'Mar, J.', 'E114'),
    ('20011', 'American Government CP', '1-153 CL', 'Q3', 1, 'Sands, K.', 'B103'),
    ('0001', 'Advisory Period', '6-011 12th', 'YR', 6, 'Owens, E.', 'K101'),
    ('28436', 'Vice Principal', '7-001', 'YR', 7, 'Ho, J.', ''),
]


def _workbook(perm_id='', student_name='', year='2026-2027'):
    wb = Workbook()
    ws = wb.active
    ws.append(HEADER)
    for num, title, section, term, period, teacher, room in ROWS:
        ws.append([perm_id, student_name, '12', num, title, section,
                   term, period, teacher, room, year])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


@pytest.fixture
def sched_env(app):
    """A counselor with one student, plus another counselor's student."""
    with app.app_context():
        User.query.filter(User.username.in_(['sch_me', 'sch_other'])).delete(
            synchronize_session=False)
        Student.query.filter(Student.student_id_number.like('SCHED-%')).delete(
            synchronize_session=False)
        db.session.commit()

        me = User(username='sch_me', display_name='Sch Me', role='counselor',
                  setup_completed=True)
        me.set_password('passw0rd123')
        other = User(username='sch_other', display_name='Sch Other',
                     role='counselor', setup_completed=True)
        other.set_password('passw0rd123')
        db.session.add_all([me, other])
        db.session.commit()

        mine = Student(student_id_number='SCHED-1', first_name='Ana',
                       last_name='Reyes', grade_level=12, status='active',
                       assigned_counselor_id=me.id)
        theirs = Student(student_id_number='SCHED-2', first_name='Bo',
                         last_name='Nguyen', grade_level=12, status='active',
                         assigned_counselor_id=other.id)
        db.session.add_all([mine, theirs])
        db.session.commit()
        ids = dict(me=me.id, other=other.id, mine=mine.id, theirs=theirs.id)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(ids['me'])
        sess['_fresh'] = True

    yield client, ids

    with app.app_context():
        ScheduleEntry.query.filter(
            ScheduleEntry.student_id.in_([ids['mine'], ids['theirs']])
        ).delete(synchronize_session=False)
        Course.query.filter(Course.course_number.in_(
            [r[0] for r in ROWS])).delete(synchronize_session=False)
        Staff.query.filter(Staff.name.in_(
            [r[5] for r in ROWS])).delete(synchronize_session=False)
        Staff.query.filter(db.func.lower(Staff.name).in_(
            [r[5].lower() for r in ROWS])).delete(synchronize_session=False)
        Student.query.filter(Student.id.in_([ids['mine'], ids['theirs']])).delete(
            synchronize_session=False)
        User.query.filter(User.id.in_([ids['me'], ids['other']])).delete(
            synchronize_session=False)
        db.session.commit()


def _import(client, buf, name='s.xlsx', **form):
    r = client.post('/data-import/schedules', data={'files': (buf, name)},
                    content_type='multipart/form-data')
    assert r.status_code == 200, 'preview failed'
    return client.post('/data-import/schedules/confirm', data=form), r


# ── matching ──

def test_matches_by_perm_id(app, sched_env):
    client, ids = sched_env
    _import(client, _workbook(perm_id='SCHED-1'), default_credits='5')
    with app.app_context():
        assert ScheduleEntry.query.filter_by(student_id=ids['mine']).count() == 4


def test_matches_by_name_when_no_id(app, sched_env):
    client, ids = sched_env
    _import(client, _workbook(student_name='Reyes, Ana'), default_credits='5')
    with app.app_context():
        assert ScheduleEntry.query.filter_by(student_id=ids['mine']).count() == 4


def test_unknown_student_is_skipped_not_invented(app, sched_env):
    client, ids = sched_env
    before = None
    with app.app_context():
        before = Student.query.count()

    _, preview = _import(client, _workbook(perm_id='NOT-ON-CASELOAD'),
                         default_credits='5')
    assert b'Not matched' in preview.data

    with app.app_context():
        assert Student.query.count() == before, 'a student was created'
        assert ScheduleEntry.query.count() == 0


def test_never_imports_onto_another_counselors_student(app, sched_env):
    """SCHED-2 belongs to the other counselor — must not be touched."""
    client, ids = sched_env
    _import(client, _workbook(perm_id='SCHED-2'), default_credits='5')
    with app.app_context():
        assert ScheduleEntry.query.filter_by(student_id=ids['theirs']).count() == 0


# ── commit behaviour ──

def test_flags_advisory_and_non_class_rows(app, sched_env):
    client, ids = sched_env
    _import(client, _workbook(perm_id='SCHED-1'), default_credits='5')
    with app.app_context():
        entries = ScheduleEntry.query.filter_by(student_id=ids['mine']).all()
        advisory = [e for e in entries if e.is_advisory]
        non_class = [e for e in entries if e.is_non_class]
        assert len(advisory) == 1 and advisory[0].period == 6
        assert '12th' in advisory[0].section_id
        assert len(non_class) == 1 and non_class[0].course_title == 'Vice Principal'


def test_credits_exclude_advisory_and_non_class(app, sched_env):
    client, ids = sched_env
    _import(client, _workbook(perm_id='SCHED-1'), default_credits='5')
    with app.app_context():
        entries = ScheduleEntry.query.filter_by(student_id=ids['mine']).all()
        total = sum(e.credits or 0 for e in entries if e.counts_for_credit)
        assert total == 10.0, 'only the two real classes should count'


def test_reimport_replaces_rather_than_duplicates(app, sched_env):
    client, ids = sched_env
    for _ in range(3):
        _import(client, _workbook(perm_id='SCHED-1'), default_credits='5')
    with app.app_context():
        assert ScheduleEntry.query.filter_by(student_id=ids['mine']).count() == 4


def test_import_seeds_the_course_catalog(app, sched_env):
    """So credits resolve automatically next year instead of being re-asked."""
    client, ids = sched_env
    _import(client, _workbook(perm_id='SCHED-1'), default_credits='5')
    with app.app_context():
        seeded = Course.query.filter_by(course_number='25248').first()
        assert seeded is not None
        assert seeded.title == 'Fashion Design CP [S1]'
        assert seeded.credits == 5.0
        # An administrative row is not a course.
        assert Course.query.filter_by(course_number='28436').first() is None


def test_import_fills_the_staff_directory(app, sched_env):
    """The directory used to stay empty until the first grades landed. A
    schedule knows every teacher on day one."""
    client, ids = sched_env
    _import(client, _workbook(perm_id='SCHED-1'), default_credits='5')
    with app.app_context():
        by_name = {s.name: s for s in Staff.query.all()}
        assert {'Mar, J.', 'Sands, K.', 'Owens, E.', 'Ho, J.'} <= set(by_name)
        assert by_name['Mar, J.'].room == 'E114'
        assert by_name['Mar, J.'].title == 'Teacher'
        # The administrative row states the real job.
        assert by_name['Ho, J.'].title == 'Administrator'
        # ...and contributes no room, since that row has none.
        assert not by_name['Ho, J.'].room


def test_import_does_not_overwrite_staff_details_the_counselor_typed(app, sched_env):
    """Re-importing must be safe: a corrected room stays corrected."""
    client, ids = sched_env
    with app.app_context():
        db.session.add(Staff(name='mar, j.', room='Portable 3',
                             email='mar@example.edu'))
        db.session.commit()
    _import(client, _workbook(perm_id='SCHED-1'), default_credits='5')
    with app.app_context():
        matches = Staff.query.filter(db.func.lower(Staff.name) == 'mar, j.').all()
        assert len(matches) == 1, 'case difference created a duplicate teacher'
        assert matches[0].room == 'Portable 3'
        assert matches[0].email == 'mar@example.edu'
        # A field that WAS blank still gets filled.
        assert matches[0].title == 'Teacher'


def test_reimporting_the_same_schedule_adds_no_duplicate_staff(app, sched_env):
    client, ids = sched_env
    _import(client, _workbook(perm_id='SCHED-1'), default_credits='5')
    with app.app_context():
        first = Staff.query.count()
    _import(client, _workbook(perm_id='SCHED-1'), default_credits='5')
    with app.app_context():
        assert Staff.query.count() == first


def test_preview_names_the_staff_that_would_be_added(app, sched_env):
    """Shown before committing, so a name misspelled in the SIS is caught here
    instead of quietly becoming a second teacher."""
    client, ids = sched_env
    r = client.post('/data-import/schedules',
                    data={'files': (_workbook(perm_id='SCHED-1'), 's.xlsx')},
                    content_type='multipart/form-data')
    html = r.data.decode()
    assert 'Staff directory' in html
    assert 'Mar, J.' in html and 'Ho, J.' in html


def test_preview_summaries_cover_a_file_whose_identity_is_unreadable(app, sched_env):
    """A redacted single-student file puts every row in `unmatched` until the
    counselor assigns it on this very page — those rows still import, so
    summarising only the matched ones showed nothing at all."""
    client, ids = sched_env
    # Neither a perm ID nor a name — the redacted printout case.
    r = client.post('/data-import/schedules',
                    data={'files': (_workbook(), 's.xlsx')},
                    content_type='multipart/form-data')
    html = r.data.decode()
    assert 'Choose student' in html, 'fixture should hit the manual-pick path'
    assert 'Staff directory' in html, 'staff summary vanished on the pick path'
    assert 'Section IDs captured' in html, 'section summary vanished on the pick path'


def test_known_catalog_credits_win_over_the_default(app, sched_env):
    client, ids = sched_env
    with app.app_context():
        db.session.add(Course(course_number='25248', title='Fashion Design',
                              credits=2.5, is_active=True))
        db.session.commit()

    _import(client, _workbook(perm_id='SCHED-1'), default_credits='5')
    with app.app_context():
        entry = ScheduleEntry.query.filter_by(
            student_id=ids['mine'], course_number='25248').first()
        assert entry.credits == 2.5


def test_credits_left_blank_when_no_default_given(app, sched_env):
    """Better an honest blank than a wrong number silently counted."""
    client, ids = sched_env
    _import(client, _workbook(perm_id='SCHED-1'))
    with app.app_context():
        entry = ScheduleEntry.query.filter_by(
            student_id=ids['mine'], course_number='25248').first()
        assert entry.credits is None


# ── the real files, end to end ──

@pytest.mark.skipif(not SAMPLE_XLS.exists(), reason='sample .xls absent')
def test_real_synergy_xls_round_trip(app, sched_env):
    """Legacy BIFF .xls, straight from Synergy, with a Perm ID patched in."""
    import xlrd
    client, ids = sched_env
    book = xlrd.open_workbook(SAMPLE_XLS)
    sheet = book.sheet_by_index(0)
    wb = Workbook()
    ws = wb.active
    for r in range(sheet.nrows):
        row = [sheet.cell_value(r, c) for c in range(sheet.ncols)]
        if r > 0:
            row[0] = 'SCHED-1'
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    _import(client, buf, default_credits='5')
    with app.app_context():
        entries = ScheduleEntry.query.filter_by(student_id=ids['mine']).all()
        assert len(entries) == 18
        assert {e.period for e in entries} == {1, 2, 3, 4, 6, 7}
        assert sum(e.credits or 0 for e in entries if e.counts_for_credit) == 80.0


@pytest.mark.skipif(not SAMPLE_PDF.exists(), reason='sample .pdf absent')
def test_real_pdf_offers_manual_student_pick_when_identity_redacted(app, sched_env):
    client, ids = sched_env
    with open(SAMPLE_PDF, 'rb') as f:
        buf = io.BytesIO(f.read())

    preview = client.post('/data-import/schedules',
                          data={'files': (buf, 'sched.pdf')},
                          content_type='multipart/form-data')
    assert preview.status_code == 200
    assert b'Choose student' in preview.data, 'no way to assign the schedule'

    client.post('/data-import/schedules/confirm',
                data={'manual_student_id': str(ids['mine']), 'default_credits': '5'})
    with app.app_context():
        entries = ScheduleEntry.query.filter_by(student_id=ids['mine']).all()
        assert len(entries) == 18
        assert all(e.source == 'pdf' for e in entries)


# ── access control ──

def test_import_routes_require_login(app):
    anon = app.test_client()
    assert anon.get('/data-import/schedules').status_code in (302, 401)
    assert anon.post('/data-import/schedules/confirm').status_code in (302, 401)


def test_preview_survives_a_payload_larger_than_a_session_cookie(app, sched_env):
    """The bug that broke every single import.

    The preview used to live in the session, which Flask backs with a signed
    COOKIE capped at ~4KB. One student's 18 schedule rows serialise to ~6KB, so
    Werkzeug silently declined to set the cookie and the confirm step always
    reported "That preview expired" — the user could never import anything.
    Staged server-side now, with only a token in the session.
    """
    import json as _json
    from app.routes.data_import.schedules import PREVIEW_KEY

    client, ids = sched_env
    r = client.post('/data-import/schedules',
                    data={'files': (_workbook(perm_id='SCHED-1'), 's.xlsx')},
                    content_type='multipart/form-data')
    assert r.status_code == 200

    with client.session_transaction() as sess:
        token = sess.get(PREVIEW_KEY)
    assert token, 'nothing was staged'
    assert len(token) < 200, 'the payload itself is back in the session'

    confirm = client.post('/data-import/schedules/confirm',
                          data={'default_credits': '5'}, follow_redirects=True)
    assert b'no longer available' not in confirm.data
    with app.app_context():
        assert ScheduleEntry.query.filter_by(student_id=ids['mine']).count() == 4


@pytest.mark.skipif(not SAMPLE_XLS.exists(), reason='sample .xls absent')
def test_real_sized_payload_would_not_fit_in_a_cookie(app):
    """Guards the reasoning, not just the behaviour: if this ever fits in 4KB
    the staging indirection could be dropped — it does not."""
    import json as _json
    from app.utils.schedule_parser import parse_schedule_file
    with open(SAMPLE_XLS, 'rb') as f:
        rows = parse_schedule_file(f, 'x.xls')
    payload = _json.dumps([r.__dict__ for r in rows], default=str)
    assert len(payload) > 4093, 'one student now fits in a cookie; re-check staging'


def test_stale_preview_files_are_purged(app, tmp_path, monkeypatch):
    import time as _time
    from app.routes.data_import import schedules as mod

    monkeypatch.setattr(mod, '_preview_dir', lambda: str(tmp_path))
    token = mod._stash_preview({'matched': [], 'unmatched': []})
    stale = tmp_path / 'schedule_preview_old.json'
    stale.write_text('{}')
    os.utime(stale, (_time.time() - mod.PREVIEW_TTL_SECONDS - 60,) * 2)

    mod._purge_stale_previews()
    assert not stale.exists(), 'abandoned preview was not cleaned up'
    assert mod._take_preview(token) is not None, 'a fresh preview was purged'


def test_preview_is_consumed_so_it_cannot_double_import(app, sched_env):
    client, ids = sched_env
    client.post('/data-import/schedules',
                data={'files': (_workbook(perm_id='SCHED-1'), 's.xlsx')},
                content_type='multipart/form-data')
    client.post('/data-import/schedules/confirm', data={'default_credits': '5'})
    again = client.post('/data-import/schedules/confirm',
                        data={'default_credits': '5'}, follow_redirects=True)
    assert b'no longer available' in again.data
    with app.app_context():
        assert ScheduleEntry.query.filter_by(student_id=ids['mine']).count() == 4


def test_expired_preview_does_not_commit(app, sched_env):
    client, ids = sched_env
    r = client.post('/data-import/schedules/confirm', data={'default_credits': '5'})
    assert r.status_code == 302
    with app.app_context():
        assert ScheduleEntry.query.filter_by(student_id=ids['mine']).count() == 0
