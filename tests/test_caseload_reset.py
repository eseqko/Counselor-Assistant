"""Caseload reset: deletes MY students and everything attached to them, and
nothing else — not the course catalog, school settings, other counselors'
students, school-wide shadow records, or my account. Distinct from the
factory reset, which wipes the whole database and restarts setup.
"""
import json
import os
from datetime import date

import pytest
from flask import url_for

from app import db
from app.models.activity import Activity
from app.models.attendance import AttendanceRecord
from app.models.course import Course, Department
from app.models.document import StudentDocument
from app.models.goal import Goal, GoalProgress
from app.models.grade import GradeRecord
from app.models.note import Note
from app.models.post_grad import PostGradOutcome
from app.models.rollover import RolloverSnapshot
from app.models.student import Student, Tag, student_tags
from app.models.user import User

_USERS = ['rst_me', 'rst_other']


def _scrub():
    uids = [u.id for u in User.query.filter(User.username.in_(_USERS)).all()]
    sids = [s.id for s in Student.query.filter(
        Student.student_id_number.like('RST-%')).all()]
    if sids:
        for model in (Note, AttendanceRecord, GradeRecord, StudentDocument, PostGradOutcome):
            model.query.filter(model.student_id.in_(sids)).delete(synchronize_session=False)
        gids = [g.id for g in Goal.query.filter(Goal.student_id.in_(sids)).all()]
        if gids:
            GoalProgress.query.filter(GoalProgress.goal_id.in_(gids)).delete(
                synchronize_session=False)
        Goal.query.filter(Goal.student_id.in_(sids)).delete(synchronize_session=False)
        db.session.execute(student_tags.delete().where(student_tags.c.student_id.in_(sids)))
    Student.query.filter(Student.student_id_number.like('RST-%')).delete(
        synchronize_session=False)
    Tag.query.filter_by(name='rst-tag').delete(synchronize_session=False)
    Course.query.filter_by(course_number='RST-101').delete(synchronize_session=False)
    Department.query.filter_by(name='RST Dept').delete(synchronize_session=False)
    if uids:
        RolloverSnapshot.query.filter(RolloverSnapshot.counselor_id.in_(uids)).delete(
            synchronize_session=False)
        Activity.query.filter(Activity.counselor_id.in_(uids)).delete(
            synchronize_session=False)
    User.query.filter(User.username.in_(_USERS)).delete(synchronize_session=False)
    db.session.commit()


@pytest.fixture
def reset_env(app):
    """Me (logged in) with two students + attached records, another counselor
    with a student, a shadow student, catalog rows, and my own non-student data."""
    with app.app_context():
        db.session.rollback()
        _scrub()
        me = User(username='rst_me', display_name='Rst Me', role='counselor',
                  setup_completed=True)
        me.set_password('passw0rd123')
        other = User(username='rst_other', display_name='Rst Other', role='counselor',
                     setup_completed=True)
        other.set_password('passw0rd123')
        db.session.add_all([me, other])
        db.session.commit()

        def student(sid, counselor_id, **kw):
            s = Student(student_id_number=sid, first_name='F', last_name=sid,
                        grade_level=10, status=kw.pop('status', 'active'),
                        assigned_counselor_id=counselor_id, **kw)
            db.session.add(s)
            return s

        a = student('RST-A', me.id)
        b = student('RST-B', me.id, status='graduated')      # exited, still mine
        o = student('RST-O', other.id)
        sh = student('RST-SH', None, is_shadow=True)         # school-wide record
        db.session.commit()

        tag = Tag(name='rst-tag')
        db.session.add(tag)
        a.tags.append(tag)
        db.session.add_all([
            Note(student_id=a.id, author_id=me.id, note_type='academic',
                 title='n', content='c'),
            Note(student_id=o.id, author_id=other.id, note_type='academic',
                 title='theirs', content='c'),
            AttendanceRecord(student_id=a.id, date=date(2026, 3, 2), status='absent'),
            GradeRecord(student_id=a.id, course_name='Algebra', letter_grade='B'),
            StudentDocument(student_id=a.id, counselor_id=me.id, document_type='iep',
                            title='doc', filename='rst-nonexistent.pdf'),
            PostGradOutcome(student_id=b.id, counselor_id=me.id,
                            primary_pathway='workforce'),
            Department(name='RST Dept'),
            Course(course_number='RST-101', title='Reset 101'),
            Activity(counselor_id=me.id, title='Lesson', date=date(2026, 3, 2),
                     service_type='direct', duration_minutes=30),
            RolloverSnapshot(counselor_id=me.id, student_count=1,
                             school_year_end_date=date(2026, 6, 1), payload='[]'),
        ])
        db.session.commit()
        goal = Goal(student_id=a.id, counselor_id=me.id, title='g')
        db.session.add(goal)
        db.session.commit()
        db.session.add(GoalProgress(goal_id=goal.id, note='p'))
        db.session.commit()
        ids = dict(me=me.id, other=other.id, a=a.id, b=b.id, o=o.id, sh=sh.id,
                   goal=goal.id, tag=tag.id)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(ids['me'])
        sess['_fresh'] = True
    yield client, ids
    with app.app_context():
        db.session.rollback()
        _scrub()


def _reset(app, client, confirm='CASELOAD'):
    with app.test_request_context():
        url = url_for('settings.caseload_reset')
    return client.post(url, data={'confirm': confirm}, follow_redirects=False)


def test_reset_deletes_my_students_and_everything_attached(app, reset_env):
    client, ids = reset_env
    r = _reset(app, client)
    assert r.status_code in (200, 302)
    with app.app_context():
        assert db.session.get(Student, ids['a']) is None
        assert db.session.get(Student, ids['b']) is None       # exited ones too
        sids = [ids['a'], ids['b']]
        for model in (Note, AttendanceRecord, GradeRecord, StudentDocument, PostGradOutcome):
            assert model.query.filter(model.student_id.in_(sids)).count() == 0, model
        assert db.session.get(Goal, ids['goal']) is None
        assert GoalProgress.query.filter_by(goal_id=ids['goal']).count() == 0
        assert db.session.execute(student_tags.select().where(
            student_tags.c.student_id.in_(sids))).first() is None
        # Undo snapshots would resurrect the deleted students.
        assert RolloverSnapshot.query.filter_by(counselor_id=ids['me']).count() == 0


def test_reset_keeps_everything_that_is_not_my_caseload(app, reset_env):
    client, ids = reset_env
    _reset(app, client)
    with app.app_context():
        # Another counselor's student and their note: untouched.
        assert db.session.get(Student, ids['o']) is not None
        assert Note.query.filter_by(student_id=ids['o']).count() == 1
        # School-wide shadow record: untouched (it's not on anyone's caseload).
        assert db.session.get(Student, ids['sh']) is not None
        # The school setup survives: catalog rows, tags, my non-student data.
        assert Course.query.filter_by(course_number='RST-101').count() == 1
        assert Department.query.filter_by(name='RST Dept').count() == 1
        assert db.session.get(Tag, ids['tag']) is not None
        assert Activity.query.filter_by(counselor_id=ids['me']).count() == 1
        # My account still exists ...
        assert db.session.get(User, ids['me']) is not None
    # ... and I'm still logged in, landing on an empty caseload rather than setup.
    with app.test_request_context():
        caseload_url = url_for('caseload.index')
    r = client.get(caseload_url)
    assert r.status_code == 200


def test_reset_requires_the_confirmation_word(app, reset_env):
    client, ids = reset_env
    r = _reset(app, client, confirm='RESET')      # the FACTORY reset's word
    assert r.status_code in (200, 302)
    with app.app_context():
        assert db.session.get(Student, ids['a']) is not None
        assert Note.query.filter_by(student_id=ids['a']).count() == 1


def test_reset_purges_only_my_followups_json(app, reset_env):
    client, ids = reset_env
    from config import DATA_DIR
    path = os.path.join(DATA_DIR, 'followups.json')
    backup = open(path).read() if os.path.exists(path) else None
    try:
        with open(path, 'w') as f:
            json.dump([
                {'id': '1', 'counselor_id': ids['me'], 'student_name': 'Mine'},
                {'id': '2', 'counselor_id': ids['other'], 'student_name': 'Theirs'},
            ], f)
        _reset(app, client)
        with open(path) as f:
            left = json.load(f)
        assert [e['student_name'] for e in left] == ['Theirs']
    finally:
        if backup is not None:
            open(path, 'w').write(backup)
        elif os.path.exists(path):
            os.remove(path)


def test_reset_snapshots_the_database_before_deleting(app, reset_env, monkeypatch):
    """The backup must be taken BEFORE anything is deleted, and the success
    message must only mention it when one was actually written."""
    import app.routes.settings as settings_mod
    client, ids = reset_env
    seen = {}

    def fake_snapshot(label):
        # Called while my students still exist → the copy would contain them.
        with app.app_context():
            seen['label'] = label
            seen['students_at_call'] = Student.query.filter_by(
                assigned_counselor_id=ids['me']).count()
        return '/backups/counselor_pre_caseload_reset_x.db'

    monkeypatch.setattr(settings_mod, 'snapshot_database', fake_snapshot)
    r = _reset(app, client)
    assert seen == {'label': 'pre_caseload_reset', 'students_at_call': 2}
    page = client.get(r.headers['Location']).get_data(as_text=True)
    assert 'backup copy' in page and 'No backup copy' not in page


def test_reset_still_runs_but_warns_when_no_backup_could_be_written(app, reset_env, monkeypatch):
    """snapshot_database never raises — None means no copy. The reset goes
    ahead (that is the app-wide convention for pre-flight snapshots) but the
    counselor is told plainly that there is no backup."""
    import app.routes.settings as settings_mod
    client, ids = reset_env
    monkeypatch.setattr(settings_mod, 'snapshot_database', lambda label: None)
    r = _reset(app, client)
    with app.app_context():
        assert db.session.get(Student, ids['a']) is None
    page = client.get(r.headers['Location']).get_data(as_text=True)
    assert 'No backup copy could be written' in page
