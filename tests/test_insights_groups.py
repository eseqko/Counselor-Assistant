"""Insights 360 by student group: a Group filter scopes every number on the
page to English Learners / non-EL / IEP / ... while the year dropdown and the
"By student group" table stay whole-caseload; an empty group is reported as
such rather than as an empty caseload."""
from datetime import date, timedelta

import pytest

from app import db
from app.models.attendance import AttendanceRecord
from app.models.grade import GradeRecord
from app.models.student import Student
from app.models.user import User

YEAR = '2026-2027'


def _scrub():
    sids = [s.id for s in Student.query.filter(Student.student_id_number.like('INS-%')).all()]
    if sids:
        GradeRecord.query.filter(GradeRecord.student_id.in_(sids)).delete(synchronize_session=False)
        AttendanceRecord.query.filter(AttendanceRecord.student_id.in_(sids)).delete(synchronize_session=False)
    Student.query.filter(Student.student_id_number.like('INS-%')).delete(synchronize_session=False)
    User.query.filter_by(username='ins_me').delete(synchronize_session=False)
    db.session.commit()


@pytest.fixture
def ins_env(app):
    """Five students: Newcomer (F, 3 absences), LTEL (D), RFEP (A),
    EO with an IEP (F, 1 absence), EO (B)."""
    with app.app_context():
        db.session.rollback()
        _scrub()
        me = User(username='ins_me', display_name='Ins Me', role='counselor', setup_completed=True)
        me.set_password('passw0rd123')
        db.session.add(me)
        db.session.commit()

        def student(sid, el, **kw):
            s = Student(student_id_number=sid, first_name='F', last_name=sid, grade_level=10,
                        status='active', assigned_counselor_id=me.id, el_status=el, **kw)
            db.session.add(s)
            return s

        a = student('INS-A', 'Newcomer', el_level='EL 1')
        b = student('INS-B', 'LTEL')
        c = student('INS-C', 'RFEP')
        d = student('INS-D', 'EO', iep_status=True)
        e = student('INS-E', 'EO')
        db.session.commit()

        def grade(s, course, letter):
            db.session.add(GradeRecord(student_id=s.id, course_name=course, letter_grade=letter,
                                       school_year=YEAR, quarter=1, grade_type='final'))
        grade(a, 'Math', 'F'); grade(b, 'English', 'D'); grade(c, 'Math', 'A')
        grade(d, 'Science', 'F'); grade(e, 'Math', 'B')
        for s, n in ((a, 3), (d, 1)):
            for i in range(n):
                db.session.add(AttendanceRecord(student_id=s.id, status='absent', period=1,
                                                date=date.today() - timedelta(days=10 + i)))
        db.session.commit()
        ids = dict(me=me.id, a=a.id, b=b.id, c=c.id, d=d.id, e=e.id)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(ids['me'])
        sess['_fresh'] = True
    yield client, ids
    with app.app_context():
        db.session.rollback()
        _scrub()


def _get(client, **params):
    qs = '&'.join(f'{k}={v}' for k, v in {'year': YEAR, **params}.items())
    r = client.get(f'/analytics/api/insights?{qs}')
    assert r.status_code == 200
    return r.get_json()


def test_default_is_whole_caseload_with_group_counts(app, ins_env):
    client, ids = ins_env
    d = _get(client)
    assert d['filters']['group'] == 'all'
    assert d['filters']['group_counts'] == {
        'all': 5, 'el': 2, 'non_el': 3, 'newcomer': 1, 'ltel': 1, 'rfep': 1, 'eo': 2,
        'iep': 1, 'no_iep': 4, 'plan_504': 0, 'any_plan': 1, 'no_plan': 4}
    assert d['summary']['total_df'] == 3 and d['summary']['failing_students'] == 3
    assert d['summary']['total_absences'] == 4


def test_group_filter_scopes_every_number(app, ins_env):
    client, ids = ins_env
    el = _get(client, group='el')
    assert el['filters']['group_label'] == 'English Learners (current)'
    assert el['summary']['total_df'] == 2 and el['summary']['failing_students'] == 2
    assert el['summary']['total_absences'] == 3
    non_el = _get(client, group='non_el')                  # RFEP + both EO
    assert non_el['summary']['total_df'] == 1 and non_el['summary']['total_absences'] == 1
    iep = _get(client, group='iep')
    assert iep['summary']['total_df'] == 1 and iep['summary']['total_absences'] == 1
    rfep = _get(client, group='rfep')
    assert rfep['summary']['total_df'] == 0
    # The year dropdown is computed from the whole caseload, so a group with
    # clean grades still offers the year.
    assert rfep['filters']['years'] == [YEAR]


def test_empty_group_is_reported_as_such(app, ins_env):
    client, ids = ins_env
    d = _get(client, group='plan_504')
    assert d.get('empty_group') is True and 'empty' not in d
    assert d['filters']['group'] == 'plan_504' and d['filters']['group_counts']['plan_504'] == 0


def test_unknown_group_falls_back_to_all(app, ins_env):
    client, ids = ins_env
    assert _get(client, group='bogus')['filters']['group'] == 'all'


def test_breakdown_splits_the_whole_caseload(app, ins_env):
    client, ids = ins_env
    for group in ('all', 'el'):          # same table whichever group is selected
        gb = _get(client, group=group)['group_breakdown']
        assert [s['title'] for s in gb] == ['EL status', 'Special education']
        el, non_el = gb[0]['rows']
        assert (el['key'], el['students'], el['graded']) == ('el', 2, 2)
        assert el['fail_pct'] == 50.0 and el['df_pct'] == 100.0      # A: F, B: D
        assert el['df_grades'] == 2 and el['absences'] == 3 and el['absences_per_student'] == 1.5
        assert (non_el['students'], non_el['graded']) == (3, 3)
        assert non_el['fail_pct'] == 33.3 and non_el['df_pct'] == 33.3   # only D's F
        assert gb[0]['df_delta'] == 66.7
        iep, no_iep = gb[1]['rows']
        assert (iep['students'], iep['fail_pct'], iep['absences']) == (1, 100.0, 1)
        assert (no_iep['students'], no_iep['df_pct']) == (4, 50.0)     # A, B of 4
