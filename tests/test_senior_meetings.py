"""Senior / Post-Secondary 1:1 meetings: scoping, the live page, autosave,
the checklist syncing the College & Career plan, deadlines, completion into a
Note + calendar reminder, the handout, and the school-wide deadline list."""
from datetime import date, timedelta

import pytest

from app import db
from app.models.calendar_event import CalendarEvent
from app.models.college_career import CollegeCareerPlan, CollegeApplication
from app.models.goal import Goal
from app.models.note import Note
from app.models.senior_meeting import SeniorMeeting, SeniorChecklistItem, PostSecondaryDeadline
from app.models.student import Student
from app.models.user import User

TODAY = date.today()


def _scrub():
    sids = [s.id for s in Student.query.filter(Student.student_id_number.like('SNR-%')).all()]
    if sids:
        SeniorChecklistItem.query.filter(SeniorChecklistItem.student_id.in_(sids)).delete(synchronize_session=False)
        SeniorMeeting.query.filter(SeniorMeeting.student_id.in_(sids)).delete(synchronize_session=False)
        Note.query.filter(Note.student_id.in_(sids)).delete(synchronize_session=False)
        CalendarEvent.query.filter(CalendarEvent.student_id.in_(sids)).delete(synchronize_session=False)
        Goal.query.filter(Goal.student_id.in_(sids)).delete(synchronize_session=False)
        plan_ids = [p.id for p in CollegeCareerPlan.query.filter(CollegeCareerPlan.student_id.in_(sids)).all()]
        if plan_ids:
            CollegeApplication.query.filter(CollegeApplication.plan_id.in_(plan_ids)).delete(synchronize_session=False)
            CollegeCareerPlan.query.filter(CollegeCareerPlan.id.in_(plan_ids)).delete(synchronize_session=False)
    Student.query.filter(Student.student_id_number.like('SNR-%')).delete(synchronize_session=False)
    PostSecondaryDeadline.query.delete(synchronize_session=False)
    User.query.filter(User.username.in_(['snr_me', 'snr_other'])).delete(synchronize_session=False)
    db.session.commit()


@pytest.fixture
def env(app):
    """Two counselors. Mine: a 4-year senior with a planned application and an
    open goal, an undecided senior, a junior, and the sample student. Theirs:
    one senior."""
    with app.app_context():
        db.session.rollback()
        _scrub()
        me = User(username='snr_me', display_name='Snr Me', role='counselor', setup_completed=True)
        me.set_password('passw0rd123')
        other = User(username='snr_other', display_name='Snr Other', role='counselor', setup_completed=True)
        other.set_password('passw0rd123')
        db.session.add_all([me, other])
        db.session.commit()

        def student(num, first, grade, counselor, **kw):
            s = Student(student_id_number=num, first_name=first, last_name='Senior', grade_level=grade,
                        status='active', assigned_counselor_id=counselor, **kw)
            db.session.add(s)
            return s

        a = student('SNR-A', 'Ana', 12, me.id)
        b = student('SNR-B', 'Ben', 12, me.id)
        j = student('SNR-J', 'Jun', 11, me.id)
        sample = student('SNR-S', 'Sample', 12, me.id, is_sample=True)
        theirs = student('SNR-T', 'Tess', 12, other.id)
        db.session.commit()
        plan = CollegeCareerPlan(student_id=a.id, counselor_id=me.id, pathway='4year')
        db.session.add(plan)
        db.session.flush()
        db.session.add(CollegeApplication(plan_id=plan.id, college_name='Cal Poly SLO', status='planned',
                                          deadline=TODAY + timedelta(days=12)))
        db.session.add(Goal(student_id=a.id, counselor_id=me.id, title='Finish PIQs', status='active',
                            target_date=TODAY + timedelta(days=20)))
        db.session.commit()
        ids = dict(me=me.id, other=other.id, a=a.id, b=b.id, j=j.id, sample=sample.id, theirs=theirs.id)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(ids['me'])
        sess['_fresh'] = True
    yield client, ids
    with app.app_context():
        db.session.rollback()
        _scrub()


def _start(client, sid):
    r = client.post(f'/senior-meetings/student/{sid}/start')
    assert r.status_code == 302, r.status_code
    return int(r.headers['Location'].rstrip('/').split('/')[-1])


# ── roster ──

def test_roster_lists_my_seniors_only(app, env):
    client, ids = env
    html = client.get('/senior-meetings/').data.decode()
    assert 'Senior, Ana' in html and 'Senior, Ben' in html
    assert 'Senior, Jun' not in html, 'juniors only with grades=all'
    assert 'Senior, Tess' not in html, "another counselor's student leaked"
    assert 'Sample' not in html, 'sample student must stay off the roster'
    assert 'Cal Poly SLO application' in html, "next date should be the student's own application"
    assert 'Senior, Jun' in client.get('/senior-meetings/?grades=all').data.decode()
    assert 'Senior, Ben' in client.get('/senior-meetings/?only=no_pathway').data.decode()
    assert 'Senior, Ana' not in client.get('/senior-meetings/?only=no_pathway').data.decode()


# ── starting and scoping ──

def test_start_creates_one_open_meeting_and_resumes_it(app, env):
    client, ids = env
    mid = _start(client, ids['a'])
    assert _start(client, ids['a']) == mid, 'a second Start should resume the open meeting'
    with app.app_context():
        m = db.session.get(SeniorMeeting, mid)
        assert m.status == 'in_progress' and m.meeting_kind == 'first' and m.pathway == '4year'
        assert m.counselor_id == ids['me']


def test_other_counselors_students_and_meetings_are_404(app, env):
    client, ids = env
    assert client.post(f'/senior-meetings/student/{ids["theirs"]}/start').status_code == 404
    assert client.get(f'/senior-meetings/student/{ids["theirs"]}').status_code == 404
    assert client.post(f'/senior-meetings/api/student/{ids["theirs"]}/checklist',
                       json={'key': 'fafsa_submitted', 'done': True}).status_code == 404
    with app.app_context():
        theirs = SeniorMeeting(student_id=ids['theirs'], counselor_id=ids['other'], meeting_date=TODAY)
        db.session.add(theirs)
        db.session.commit()
        tid = theirs.id
    for path in (f'/senior-meetings/{tid}', f'/senior-meetings/{tid}/handout'):
        assert client.get(path).status_code == 404, path
    for path in (f'/senior-meetings/api/{tid}/save', f'/senior-meetings/{tid}/complete',
                 f'/senior-meetings/{tid}/delete', f'/senior-meetings/{tid}/reopen'):
        assert client.post(path, json={'notes': 'x'}).status_code == 404, path


def test_sample_student_can_open_a_meeting_to_try_the_tool(app, env):
    client, ids = env
    mid = _start(client, ids['sample'])
    assert client.get(f'/senior-meetings/{mid}').status_code == 200


# ── the live page ──

def test_meeting_page_shows_prompts_deadlines_and_checklist(app, env):
    client, ids = env
    mid = _start(client, ids['a'])
    html = client.get(f'/senior-meetings/{mid}').data.decode()
    # SFBT and ASCA content
    assert 'Suppose tonight, while you' in html, 'miracle question missing'
    assert 'SFBT · scaling' in html and 'B-LS 7' in html and 'coach tip' in html
    assert 'Since Last Time' not in html, 'follow-up prompts only on return visits'
    # deadlines for THIS student: school-wide for 4-year, their application, their goal
    assert 'UC application deadline' in html
    assert 'Cal Poly SLO application' in html and 'Finish PIQs' in html
    assert 'Community college priority registration' not in html, '2-year-only date on a 4-year pathway'
    # checklist for the pathway
    assert 'Submit UC application' in html and 'Submit the FAFSA' in html
    assert 'Take the ASVAB' not in html, 'military-only item on a 4-year pathway'
    assert 'Take the ASVAB' in client.get(f'/senior-meetings/{mid}?items=all').data.decode()


def test_autosave_persists_notes_answers_scales_and_next_step(app, env):
    client, ids = env
    mid = _start(client, ids['a'])
    due = (TODAY + timedelta(days=5)).isoformat()
    r = client.post(f'/senior-meetings/api/{mid}/save', json={
        'notes': 'Wants CSU Long Beach', 'answers': {'scale_plan_progress': 4, 'open_best_hopes': 'get aid sorted',
                                                     'bogus_key': 'ignored'},
        'scale_stress': 7, 'next_step': 'Make FSA ID', 'next_step_due': due, 'pathway': '2year'})
    d = r.get_json()
    assert r.status_code == 200 and d['ok'] and d['scale_plan'] == 4 and d['scale_stress'] == 7
    with app.app_context():
        m = db.session.get(SeniorMeeting, mid)
        assert m.notes == 'Wants CSU Long Beach' and m.next_step == 'Make FSA ID'
        assert m.next_step_due.isoformat() == due and m.scale_plan == 4
        assert m.answers == {'scale_plan_progress': '4', 'open_best_hopes': 'get aid sorted'}
        assert m.pathway == '2year'
        assert CollegeCareerPlan.query.filter_by(student_id=ids['a']).first().pathway == '2year', \
            'pathway change must reach the College & Career plan'
    html = client.get(f'/senior-meetings/{mid}').data.decode()
    assert 'Wants CSU Long Beach' in html and 'Community college priority registration' in html


def test_pathway_from_the_meeting_creates_a_plan_when_none_exists(app, env):
    client, ids = env
    mid = _start(client, ids['b'])
    client.post(f'/senior-meetings/api/{mid}/save', json={'pathway': 'military'})
    with app.app_context():
        assert CollegeCareerPlan.query.filter_by(student_id=ids['b']).first().pathway == 'military'


# ── checklist ──

def test_checklist_persists_per_student_and_syncs_the_plan(app, env):
    client, ids = env
    mid = _start(client, ids['b'])
    r = client.post(f'/senior-meetings/api/student/{ids["b"]}/checklist',
                    json={'key': 'fafsa_submitted', 'done': True, 'meeting_id': mid})
    d = r.get_json()
    assert r.status_code == 200 and d['ok'] and d['synced'] == 'fafsa_status' and d['counts']['done'] == 1
    with app.app_context():
        plan = CollegeCareerPlan.query.filter_by(student_id=ids['b']).first()
        assert plan and plan.fafsa_status == 'submitted' and plan.fafsa_submitted_date == TODAY
        row = SeniorChecklistItem.query.filter_by(student_id=ids['b'], key='fafsa_submitted').first()
        assert row.done and row.meeting_id == mid
        assert db.session.get(SeniorMeeting, mid).checked_keys == ['fafsa_submitted']
    # unknown keys are rejected
    assert client.post(f'/senior-meetings/api/student/{ids["b"]}/checklist',
                       json={'key': 'not_a_thing', 'done': True}).status_code == 400
    # un-ticking steps the plan back and drops it from the meeting
    client.post(f'/senior-meetings/api/student/{ids["b"]}/checklist',
                json={'key': 'fafsa_submitted', 'done': False, 'meeting_id': mid})
    with app.app_context():
        plan = CollegeCareerPlan.query.filter_by(student_id=ids['b']).first()
        assert plan.fafsa_status == 'in_progress' and plan.fafsa_submitted_date is None
        assert db.session.get(SeniorMeeting, mid).checked_keys == []
    # state is per student, visible on the history page without any meeting
    client.post(f'/senior-meetings/api/student/{ids["b"]}/checklist', json={'key': 'resume_done', 'done': True})
    html = client.get(f'/senior-meetings/student/{ids["b"]}').data.decode()
    assert 'data-item="resume_done" checked' in html


# ── completing ──

def test_complete_logs_a_note_with_asca_codes_and_a_calendar_reminder(app, env):
    client, ids = env
    mid = _start(client, ids['a'])
    follow = (TODAY + timedelta(days=14)).isoformat()
    client.post(f'/senior-meetings/api/{mid}/save', json={
        'notes': 'Good talk.', 'answers': {'scale_plan_progress': 5, 'miracle_question': 'I would have my list done'},
        'next_step': 'Ask Ms. Lee for a letter', 'next_step_due': (TODAY + timedelta(days=7)).isoformat(),
        'follow_up_date': follow, 'follow_up_notes': 'Check the letter', 'note_type': 'financial_aid'})
    client.post(f'/senior-meetings/api/student/{ids["a"]}/checklist',
                json={'key': 'college_list', 'done': True, 'meeting_id': mid})
    r = client.post(f'/senior-meetings/{mid}/complete')
    assert r.status_code == 302
    with app.app_context():
        m = db.session.get(SeniorMeeting, mid)
        assert m.status == 'completed' and m.completed_at and m.note_id
        n = db.session.get(Note, m.note_id)
        assert n.student_id == ids['a'] and n.author_id == ids['me']
        assert n.note_type == 'financial_aid' and n.asca_domain in ('career', 'academic', 'social_emotional')
        assert 'M 4' in n.asca_standard and 'B-LS 7' in n.asca_standard
        for phrase in ('Good talk.', 'Ask Ms. Lee for a letter', 'I would have my list done',
                       'Build a college list', 'plan handled 5/10', 'Counselor follow-up'):
            assert phrase in n.content, phrase
        assert n.follow_up_needed and n.follow_up_date.isoformat() == follow and n.is_confidential
        events = CalendarEvent.query.filter_by(student_id=ids['a'], event_type='follow_up').all()
        assert len(events) == 1 and events[0].start_datetime.date().isoformat() == follow
    html = client.get(f'/senior-meetings/{mid}').data.decode()
    assert 'Meeting summary' in html and 'Reopen to edit' in html
    assert client.post(f'/senior-meetings/api/{mid}/save', json={'notes': 'late'}).status_code == 409
    # the profile timeline now shows it, and the profile card counts it
    profile = client.get(f'/caseload/{ids["a"]}').data.decode()
    assert 'Senior Meetings (1)' in profile
    # re-completing after a reopen updates the same note and adds no second reminder
    client.post(f'/senior-meetings/{mid}/reopen')
    client.post(f'/senior-meetings/api/{mid}/save', json={'notes': 'Good talk. Added more.'})
    client.post(f'/senior-meetings/{mid}/complete')
    with app.app_context():
        assert Note.query.filter_by(student_id=ids['a']).count() == 1
        assert 'Added more.' in db.session.get(Note, db.session.get(SeniorMeeting, mid).note_id).content
        assert CalendarEvent.query.filter_by(student_id=ids['a'], event_type='follow_up').count() == 1


def test_second_meeting_is_a_follow_up_that_shows_last_time(app, env):
    client, ids = env
    first = _start(client, ids['a'])
    client.post(f'/senior-meetings/api/{first}/save', json={'scale_plan': 3, 'next_step': 'Make FSA ID',
                                                            'next_step_due': (TODAY + timedelta(days=3)).isoformat()})
    client.post(f'/senior-meetings/{first}/complete')
    second = _start(client, ids['a'])
    assert second != first
    html = client.get(f'/senior-meetings/{second}').data.decode()
    assert 'Since Last Time' in html and 'better since we last met' in html
    assert 'Their step: Make FSA ID' in html and 'last 3' in html
    r = client.post(f'/senior-meetings/api/{first}/step-done', json={'done': True})
    assert r.get_json()['done'] is True
    with app.app_context():
        assert db.session.get(SeniorMeeting, second).meeting_kind == 'followup'
        assert db.session.get(SeniorMeeting, first).next_step_done


def test_delete_keeps_the_note_and_the_ticked_boxes(app, env):
    client, ids = env
    mid = _start(client, ids['a'])
    client.post(f'/senior-meetings/api/student/{ids["a"]}/checklist',
                json={'key': 'brag_sheet', 'done': True, 'meeting_id': mid})
    client.post(f'/senior-meetings/{mid}/complete')
    r = client.post(f'/senior-meetings/{mid}/delete')
    assert r.status_code == 302
    with app.app_context():
        assert db.session.get(SeniorMeeting, mid) is None
        assert Note.query.filter_by(student_id=ids['a']).count() == 1
        row = SeniorChecklistItem.query.filter_by(student_id=ids['a'], key='brag_sheet').first()
        assert row.done and row.meeting_id is None


# ── handout ──

def test_handout_is_a_standalone_page_for_the_student(app, env):
    client, ids = env
    mid = _start(client, ids['a'])
    client.post(f'/senior-meetings/api/{mid}/save', json={'next_step': 'Email the Cal Poly admissions office',
                                                          'answers': {'sup_go_to_adult': 'Ms. Lee, room 12'}})
    html = client.get(f'/senior-meetings/{mid}/handout').data.decode()
    assert 'Email the Cal Poly admissions office' in html and 'Ms. Lee, room 12' in html
    assert 'Cal Poly SLO application' in html and 'Still on my list' in html
    assert 'class="sidebar"' not in html, 'handout must not carry the app chrome'


# ── school-wide deadlines ──

def test_deadlines_page_loads_defaults_and_edits_for_admins_only(app, env):
    client, ids = env
    html = client.get('/senior-meetings/deadlines').data.decode()
    assert 'Only an admin can change' in html
    r = client.post('/senior-meetings/deadlines', data={'action': 'load_defaults'}, follow_redirects=False)
    with app.app_context():
        assert PostSecondaryDeadline.query.count() == 0, 'a plain counselor in a multi-user install cannot load'
        User.query.filter_by(id=ids['me']).update({'role': 'admin'})
        db.session.commit()
    client.post('/senior-meetings/deadlines', data={'action': 'load_defaults'})
    with app.app_context():
        n = PostSecondaryDeadline.query.count()
        assert n >= 27
        uc = PostSecondaryDeadline.query.filter_by(key='uc_app_deadline').first()
        assert uc and uc.date.isoformat() == '2026-11-30'
    client.post('/senior-meetings/deadlines', data={'action': 'load_defaults'})
    with app.app_context():
        assert PostSecondaryDeadline.query.count() == n, 'loading twice must not duplicate'
    client.post('/senior-meetings/deadlines', data={'action': 'update', 'id': uc.id, 'label': 'UC application deadline',
                                                    'date': '2026-12-01', 'pathways': ['4year'], 'category': 'application',
                                                    'source': 'UCOP'})
    client.post('/senior-meetings/deadlines', data={'action': 'add', 'label': 'Senior scholarship night',
                                                    'date': (TODAY + timedelta(days=30)).isoformat(),
                                                    'pathways': ['all'], 'category': 'financial_aid'})
    with app.app_context():
        assert db.session.get(PostSecondaryDeadline, uc.id).date.isoformat() == '2026-12-01'
        assert not db.session.get(PostSecondaryDeadline, uc.id).verify
    mid = _start(client, ids['a'])
    html = client.get(f'/senior-meetings/{mid}').data.decode()
    assert 'Senior scholarship night' in html and 'Dec 1' in html


# ── housekeeping ──

def test_caseload_reset_removes_meetings_and_checklist_rows(app, env):
    client, ids = env
    from app.utils.caseload_reset import delete_students_with_dependents
    mid = _start(client, ids['a'])
    client.post(f'/senior-meetings/api/student/{ids["a"]}/checklist', json={'key': 'brag_sheet', 'done': True})
    client.post(f'/senior-meetings/{mid}/complete')
    with app.app_context():
        counts = delete_students_with_dependents([ids['a']])
        db.session.commit()
        assert counts.get('senior_meetings') == 1 and counts.get('senior_checklist_items') == 1
        assert SeniorMeeting.query.filter_by(student_id=ids['a']).count() == 0
        assert db.session.get(Student, ids['a']) is None
