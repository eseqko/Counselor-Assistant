"""Cross-counselor access control: B must never reach A's records.

The route-smoke sweep only checks for 500s, so an IDOR returns a perfectly
healthy 200 and passes it. This file is the gate that keeps the bug class dead:
counselor B requests each of counselor A's records by primary key and must get
404 — not 403, which would confirm the record exists (FERPA enumeration).

Sites covered are the ones found unguarded in the 2026-07-28 review:
notes fed to the LLM (ai.py), counseling groups and their child rows, college
applications / test scores, ASCA program reports, screening templates, and
activity-log entries.
"""
from datetime import date

import pytest

from app import db
from app.models.activity import Activity
from app.models.asca_program import ASCAProgram
# Aliased: a bare `TestScore` name gets collected by pytest as a test class.
from app.models.college_career import (CollegeCareerPlan, CollegeApplication,
                                       TestScore as TestScoreModel)
from app.models.group import CounselingGroup, GroupMember, GroupSession
from app.models.note import Note
from app.models.screening import ScreeningTemplate
from app.models.student import Student
from app.models.user import User

# The model's __name__ is still 'TestScore', so pytest tries to collect it.
TestScoreModel.__test__ = False


@pytest.fixture
def two_counselors(app):
    """Counselor A owning one of everything, and counselor B logged in."""
    with app.app_context():
        # A previous aborted run can leave these behind (shared session DB).
        User.query.filter(User.username.in_(['scope_a', 'scope_b'])).delete(
            synchronize_session=False)
        Student.query.filter_by(student_id_number='SCOPE-A1').delete(
            synchronize_session=False)
        db.session.commit()

        a = User(username='scope_a', display_name='Scope A', role='counselor',
                 setup_completed=True)
        a.set_password('passw0rd123')
        b = User(username='scope_b', display_name='Scope B', role='counselor',
                 setup_completed=True)
        b.set_password('passw0rd123')
        db.session.add_all([a, b])
        db.session.commit()

        student = Student(student_id_number='SCOPE-A1', first_name='Ann',
                          last_name='Alpha', grade_level=11, status='active',
                          assigned_counselor_id=a.id)
        db.session.add(student)
        db.session.commit()

        note = Note(student_id=student.id, author_id=a.id, note_type='academic',
                    title='Private', content='Confidential counseling content.')
        group = CounselingGroup(name="Grief and Loss", counselor_id=a.id)
        plan = CollegeCareerPlan(student_id=student.id, counselor_id=a.id)
        prog = ASCAProgram(counselor_id=a.id, name='Closing the Gap 2026')
        tmpl = ScreeningTemplate(counselor_id=a.id, name='PHQ-9 (custom)',
                                 questions_json='[]')
        act = Activity(counselor_id=a.id, title='Classroom lesson',
                       date=date(2026, 5, 1), service_type='direct',
                       duration_minutes=45)
        db.session.add_all([note, group, plan, prog, tmpl, act])
        db.session.commit()

        member = GroupMember(group_id=group.id, student_id=student.id)
        gsession = GroupSession(group_id=group.id, topic='Session 1',
                                session_date=date(2026, 5, 1))
        capp = CollegeApplication(plan_id=plan.id, college_name='State U')
        tscore = TestScoreModel(plan_id=plan.id, test_type='SAT')
        db.session.add_all([member, gsession, capp, tscore])
        db.session.commit()

        ids = dict(a=a.id, b=b.id, student=student.id, note=note.id,
                   group=group.id, member=member.id, gsession=gsession.id,
                   plan=plan.id, capp=capp.id, tscore=tscore.id,
                   prog=prog.id, tmpl=tmpl.id, act=act.id)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(ids['b'])
        sess['_fresh'] = True

    yield client, ids

    with app.app_context():
        for model in (GroupMember, GroupSession, CollegeApplication, TestScoreModel):
            model.query.delete(synchronize_session=False)
        for model in (Note, CounselingGroup, CollegeCareerPlan, ASCAProgram,
                      ScreeningTemplate, Activity):
            model.query.filter_by(
                **({'author_id': ids['a']} if model is Note else {'counselor_id': ids['a']})
            ).delete(synchronize_session=False)
        Student.query.filter_by(id=ids['student']).delete(synchronize_session=False)
        User.query.filter(User.id.in_([ids['a'], ids['b']])).delete(synchronize_session=False)
        db.session.commit()


def _get_paths(ids):
    return [
        f'/groups/{ids["group"]}',
        f'/groups/{ids["group"]}/edit',
        f'/college-career/application/{ids["capp"]}/edit',
        f'/reports/asca-results/{ids["prog"]}',
        f'/reports/asca-results/{ids["prog"]}/edit',
        f'/screenings/template/{ids["tmpl"]}/administer',
        f'/screenings/template/{ids["tmpl"]}/form',
        f'/screenings/template/{ids["tmpl"]}/import-responses',
        f'/activity-log/{ids["act"]}/edit',
    ]


def test_cohort_concentration_only_counts_your_own_caseload(app, two_counselors):
    """The report aggregates rather than showing records by id, so the leak it
    could produce is counting another counselor's students into your slices."""
    client, ids = two_counselors
    r = client.get('/reports/cohort-concentration')
    assert r.status_code == 200
    # Counselor B has no students at all, so every slice must be empty —
    # counselor A's student must not appear in B's baseline.
    assert b'Import Schedules' in r.data or b'0 students' in r.data
    assert b'Ann' not in r.data


def _post_paths(ids):
    return [
        f'/groups/{ids["group"]}/delete',
        f'/groups/member/{ids["member"]}/remove',
        f'/groups/member/{ids["member"]}/update',
        f'/groups/session/{ids["gsession"]}/delete',
        f'/groups/{ids["group"]}/session/add',
        f'/college-career/application/{ids["capp"]}/delete',
        f'/college-career/test/{ids["tscore"]}/delete',
        f'/reports/asca-results/{ids["prog"]}/delete',
        f'/screenings/template/{ids["tmpl"]}/create-form',
        f'/screenings/template/{ids["tmpl"]}/post-classroom',
        f'/screenings/template/{ids["tmpl"]}/save-imports',
        f'/activity-log/{ids["act"]}/delete',
    ]


def test_every_probed_path_is_a_real_route(app, two_counselors):
    """Guard against the vacuous pass: a typo'd URL 404s for everyone, which
    would make every assertion below succeed while testing nothing."""
    _, ids = two_counselors
    adapter = app.url_map.bind('localhost')
    unmatched = []
    for method, paths in (('GET', _get_paths(ids)), ('POST', _post_paths(ids))):
        for path in paths:
            try:
                adapter.match(path, method=method)
            except Exception:
                unmatched.append(f'{method} {path}')
    assert not unmatched, 'These probe paths match no route:\n' + '\n'.join(unmatched)


def test_get_routes_deny_other_counselors_records(app, two_counselors):
    client, ids = two_counselors
    leaks = []
    for path in _get_paths(ids):
        r = client.get(path)
        if r.status_code != 404:
            leaks.append(f'{path} -> {r.status_code}')
    assert not leaks, 'Cross-counselor GET leaked:\n' + '\n'.join(leaks)


def test_post_routes_deny_other_counselors_records(app, two_counselors):
    client, ids = two_counselors
    leaks = []
    for path in _post_paths(ids):
        r = client.post(path)
        if r.status_code != 404:
            leaks.append(f'{path} -> {r.status_code}')
    assert not leaks, 'Cross-counselor POST leaked:\n' + '\n'.join(leaks)


def test_destructive_posts_did_not_actually_delete(app, two_counselors):
    """A 404 that still performed the write would be worse than a 200."""
    client, ids = two_counselors
    for path in _post_paths(ids):
        client.post(path)
    with app.app_context():
        assert db.session.get(CounselingGroup, ids['group']) is not None
        assert db.session.get(GroupMember, ids['member']) is not None
        assert db.session.get(GroupSession, ids['gsession']) is not None
        assert db.session.get(CollegeApplication, ids['capp']) is not None
        assert db.session.get(TestScoreModel, ids['tscore']) is not None
        assert db.session.get(ASCAProgram, ids['prog']) is not None
        assert db.session.get(Activity, ids['act']) is not None


def test_ai_note_feedback_denies_other_counselors_note(app, two_counselors):
    """The most sensitive one: note body + IEP/504/EL flags into an LLM prompt."""
    client, ids = two_counselors
    for path in ('/ai/note-feedback', '/ai/note-feedback-stream'):
        r = client.post(path, json={'note_id': ids['note']})
        assert r.status_code == 404, f'{path} -> {r.status_code}'


def test_owner_can_still_reach_their_own_records(app, two_counselors):
    """The guards must not lock the legitimate owner out."""
    client, ids = two_counselors
    with client.session_transaction() as sess:
        sess['_user_id'] = str(ids['a'])       # switch to the owner
        sess['_fresh'] = True
    blocked = []
    for path in _get_paths(ids):
        r = client.get(path)
        if r.status_code == 404:
            blocked.append(path)
    assert not blocked, 'Owner locked out of their own records:\n' + '\n'.join(blocked)
