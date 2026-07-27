"""New-year caseload sync: preview diff, departing actions, safety defaults, undo.

Covers the upgraded /caseload/upload flow: the three-bucket preview
(returning / new / departing), the FERPA skip for other counselors' students,
the keep-by-default safety guarantee, each departing action's field effects,
and the 24-hour undo round-trip including counselor re-assignment.
"""
import io
import json

import pytest
from openpyxl import Workbook

from app import db
from app.models.student import Student
from app.models.user import User
from app.models.rollover import RolloverSnapshot

HEADERS = ['First Name', 'Last Name', 'Grade', 'Student ID #', 'Email',
           'EL Status', 'EL Level', 'IEP', '504 Plan']


def _xlsx(rows):
    """Build an in-memory caseload-template xlsx from (first, last, grade, sid) tuples."""
    wb = Workbook()
    ws = wb.active
    ws.append(HEADERS)
    for first, last, grade, sid in rows:
        ws.append([first, last, grade, sid, '', 'EO', '', '', ''])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


@pytest.fixture
def sync_env(app):
    """A dedicated counselor with a small caseload + a shadow + a sample + a
    student owned by another counselor. Unique IDs so the shared test DB is safe."""
    with app.app_context():
        me = User(username='sync_me', display_name='Sync Me', role='counselor',
                  setup_completed=True)
        me.set_password('passw0rd123')
        other = User(username='sync_other', display_name='Sync Other',
                     role='counselor', setup_completed=True)
        other.set_password('passw0rd123')
        db.session.add_all([me, other])
        db.session.commit()

        def student(sid, counselor_id, **kw):
            s = Student(student_id_number=sid, first_name=f'F{sid}',
                        last_name=f'L{sid}', grade_level=kw.pop('grade', 9),
                        status=kw.pop('status', 'active'),
                        assigned_counselor_id=counselor_id, **kw)
            db.session.add(s)
            return s

        mine_a = student('SYNC-A', me.id, grade=9)      # returning (promoted to 10)
        mine_b = student('SYNC-B', me.id, grade=11)     # departing
        mine_c = student('SYNC-C', me.id, grade=12)     # departing
        sample = student('SYNC-SAMPLE', me.id, is_sample=True)
        shadow = student('SYNC-SHADOW', None, is_shadow=True)
        theirs = student('SYNC-THEIRS', other.id)
        db.session.commit()
        ids = dict(me=me.id, other=other.id, a=mine_a.id, b=mine_b.id,
                   c=mine_c.id, sample=sample.id, shadow=shadow.id,
                   theirs=theirs.id)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(ids['me'])
        sess['_fresh'] = True

    yield client, ids

    # Clean up so repeated fixture uses (and the shared demo DB) stay pristine.
    with app.app_context():
        Student.query.filter(Student.student_id_number.like('SYNC-%')).delete(
            synchronize_session=False)
        RolloverSnapshot.query.filter(
            RolloverSnapshot.counselor_id.in_([ids['me'], ids['other']])).delete(
            synchronize_session=False)
        User.query.filter(User.username.in_(['sync_me', 'sync_other'])).delete(
            synchronize_session=False)
        db.session.commit()


def _get(app, sid_key, ids):
    with app.app_context():
        return db.session.get(Student, ids[sid_key])


def test_preview_buckets(app, sync_env):
    client, ids = sync_env
    # File: A returns (now grade 10), NEW-1 brand new, SHADOW promotable,
    # THEIRS blocked. B, C absent -> departing. Sample must never appear.
    f = _xlsx([('Fa', 'La', 10, 'SYNC-A'), ('Fn', 'Ln', 9, 'SYNC-NEW1'),
               ('Fs', 'Ls', 9, 'SYNC-SHADOW'), ('Ft', 'Lt', 9, 'SYNC-THEIRS')])
    r = client.post('/caseload/upload/preview',
                    data={'file': (f, 'roster.xlsx')},
                    content_type='multipart/form-data')
    assert r.status_code == 200
    data = r.get_json()
    assert data['ok'] is True

    assert [x['sid'] for x in data['returning']] == ['SYNC-A']
    assert data['returning'][0]['grade_from'] == 9
    assert data['returning'][0]['grade_to'] == 10
    assert data['returning'][0]['grade_changed'] is True

    kinds = {x['sid']: x['kind'] for x in data['new']}
    assert kinds == {'SYNC-NEW1': 'brand_new', 'SYNC-SHADOW': 'promotable',
                     'SYNC-THEIRS': 'other_counselor'}

    departing_sids = {x['sid'] for x in data['departing']}
    assert departing_sids == {'SYNC-B', 'SYNC-C'}
    assert 'SYNC-SAMPLE' not in departing_sids


def test_apply_without_actions_keeps_departing(app, sync_env):
    client, ids = sync_env
    f = _xlsx([('Fa', 'La', 10, 'SYNC-A')])   # B and C absent, no actions posted
    r = client.post('/caseload/upload', data={'file': (f, 'roster.xlsx')},
                    content_type='multipart/form-data', follow_redirects=False)
    assert r.status_code in (200, 302)
    b = _get(app, 'b', ids)
    c = _get(app, 'c', ids)
    assert b.status == 'active' and b.assigned_counselor_id == ids['me']
    assert c.status == 'active' and c.assigned_counselor_id == ids['me']
    # And the returning student's grade was updated from the file.
    assert _get(app, 'a', ids).grade_level == 10


def test_apply_departing_actions(app, sync_env):
    client, ids = sync_env
    actions = {str(ids['b']): 'transfer', str(ids['c']): 'unassign'}
    f = _xlsx([('Fa', 'La', 10, 'SYNC-A')])
    r = client.post('/caseload/upload',
                    data={'file': (f, 'roster.xlsx'),
                          'departing_actions': json.dumps(actions)},
                    content_type='multipart/form-data', follow_redirects=False)
    assert r.status_code in (200, 302)

    b = _get(app, 'b', ids)
    assert b.status == 'transferred'
    assert b.exit_reason == 'transferred_out_district'
    assert b.exit_date is not None

    c = _get(app, 'c', ids)
    assert c.status == 'active'                  # unassign is NOT an exit
    assert c.assigned_counselor_id is None
    assert c.exit_reason is None

    with app.app_context():
        snap = RolloverSnapshot.query.filter_by(counselor_id=ids['me']).first()
        assert snap is not None and snap.student_count == 2


def test_undo_restores_assignment_and_status(app, sync_env):
    client, ids = sync_env
    actions = {str(ids['b']): 'graduate', str(ids['c']): 'unassign'}
    f = _xlsx([('Fa', 'La', 10, 'SYNC-A')])
    client.post('/caseload/upload',
                data={'file': (f, 'roster.xlsx'),
                      'departing_actions': json.dumps(actions)},
                content_type='multipart/form-data')
    with app.app_context():
        snap_id = RolloverSnapshot.query.filter_by(
            counselor_id=ids['me']).first().id

    r = client.post(f'/caseload/rollover/undo/{snap_id}', follow_redirects=False)
    assert r.status_code in (200, 302)

    b = _get(app, 'b', ids)
    assert b.status == 'active' and b.exit_reason is None and b.exit_date is None
    c = _get(app, 'c', ids)
    # The unassign must round-trip: counselor restored even though the
    # student was unowned at undo time.
    assert c.assigned_counselor_id == ids['me'] and c.status == 'active'


def test_ferpa_other_counselor_never_touched(app, sync_env):
    client, ids = sync_env
    # File contains THEIRS; also try to sneak a departing action against them.
    f = _xlsx([('Ft', 'Lt', 9, 'SYNC-THEIRS')])
    r = client.post('/caseload/upload',
                    data={'file': (f, 'roster.xlsx'),
                          'departing_actions': json.dumps({str(ids['theirs']): 'unassign'})},
                    content_type='multipart/form-data', follow_redirects=False)
    assert r.status_code in (200, 302)
    theirs = _get(app, 'theirs', ids)
    assert theirs.assigned_counselor_id == ids['other']   # untouched
    assert theirs.status == 'active'


def test_stale_preview_never_exits_student_in_file(app, sync_env):
    client, ids = sync_env
    # B IS in the file, but a (stale) action targets them -> must be ignored.
    f = _xlsx([('Fb', 'Lb', 12, 'SYNC-B')])
    client.post('/caseload/upload',
                data={'file': (f, 'roster.xlsx'),
                      'departing_actions': json.dumps({str(ids['b']): 'transfer'})},
                content_type='multipart/form-data')
    b = _get(app, 'b', ids)
    assert b.status == 'active' and b.assigned_counselor_id == ids['me']


def test_legacy_plain_upload_still_appends_and_updates(app, sync_env):
    client, ids = sync_env
    f = _xlsx([('NewFirst', 'NewLast', 9, 'SYNC-LEGACY'),
               ('Fa2', 'La2', 11, 'SYNC-A')])
    r = client.post('/caseload/upload', data={'file': (f, 'roster.xlsx')},
                    content_type='multipart/form-data', follow_redirects=False)
    assert r.status_code in (200, 302)
    with app.app_context():
        legacy = Student.query.filter_by(student_id_number='SYNC-LEGACY').first()
        assert legacy is not None and legacy.assigned_counselor_id == ids['me']
    a = _get(app, 'a', ids)
    assert a.grade_level == 11 and a.first_name == 'Fa2'
