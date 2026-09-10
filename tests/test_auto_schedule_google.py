"""Cohort auto-scheduler -> Google Calendar.

Confirming a proposal creates the Google events when asked (and connected),
stores each event id so a cancel can remove it, never invites students
unless asked, treats a group meeting as ONE event, and a catch-up action
pushes upcoming appointments that aren't on Google yet. The Google API is
stubbed at the module boundary the routes call through.
"""
from datetime import date, timedelta

import pytest

from app import db
import app.routes.availability as av
from app.models.availability import Booking
from app.models.calendar_event import CalendarEvent
from app.models.student import Student
from app.models.user import User

TOMORROW = (date.today() + timedelta(days=1)).isoformat()


def _scrub():
    uids = [u.id for u in User.query.filter_by(username='gcal_me').all()]
    if uids:
        Booking.query.filter(Booking.counselor_id.in_(uids)).delete(synchronize_session=False)
        CalendarEvent.query.filter(CalendarEvent.owner_id.in_(uids)).delete(synchronize_session=False)
    Student.query.filter(Student.student_id_number.like('GCAL-%')).delete(synchronize_session=False)
    User.query.filter_by(username='gcal_me').delete(synchronize_session=False)
    db.session.commit()


@pytest.fixture
def gcal_env(app, monkeypatch):
    """A connected counselor with two students; Google's API stubbed."""
    with app.app_context():
        db.session.rollback()
        _scrub()
        me = User(username='gcal_me', display_name='Gcal Me', role='counselor',
                  setup_completed=True)
        me.set_password('passw0rd123')
        db.session.add(me)
        db.session.commit()
        a = Student(student_id_number='GCAL-A', first_name='Ana', last_name='Vega',
                    grade_level=12, status='active', assigned_counselor_id=me.id,
                    email='ana@example.org')
        b = Student(student_id_number='GCAL-B', first_name='Luis', last_name='Ybarra',
                    grade_level=12, status='active', assigned_counselor_id=me.id)
        db.session.add_all([a, b])
        db.session.commit()
        ids = dict(me=me.id, a=a.id, b=b.id)

    calls = []

    def fake_create(user, summary, start_dt, end_dt, **kw):
        calls.append({'summary': summary, 'start': start_dt, 'end': end_dt, **kw})
        return {'id': f'evt-{len(calls)}', 'htmlLink': 'https://calendar.google.com/x'}

    monkeypatch.setattr(av.google_client, 'is_connected', lambda user: True)
    monkeypatch.setattr(av.google_calendar, 'create_event', fake_create)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(ids['me'])
        sess['_fresh'] = True
    yield client, ids, calls
    with app.app_context():
        db.session.rollback()
        _scrub()


def _individual_proposal(ids):
    return {
        'mode': 'individual', 'title': 'Senior Check-in', 'notes': 'Bring transcript',
        'duration': 30, 'days_ahead': 14, 'meeting_type': 'general',
        'items': [
            {'student_id': ids['a'], 'name': 'Ana Vega', 'date': TOMORROW, 'day_name': 'Day',
             'start_time': '09:00', 'end_time': '09:30', 'display': '9:00 AM - 9:30 AM'},
            {'student_id': ids['b'], 'name': 'Luis Ybarra', 'date': TOMORROW, 'day_name': 'Day',
             'start_time': '09:30', 'end_time': '10:00', 'display': '9:30 AM - 10:00 AM'},
        ],
        'unscheduled': [], 'created_at': 'x',
    }


def _set_proposal(client, proposal):
    with client.session_transaction() as sess:
        sess['auto_proposal'] = proposal


def _confirm(client, **form):
    return client.post('/scheduling/auto/confirm', data=form, follow_redirects=True)


def test_confirm_adds_each_appointment_to_google(app, gcal_env):
    client, ids, calls = gcal_env
    _set_proposal(client, _individual_proposal(ids))
    r = _confirm(client, add_to_google='1')
    assert r.status_code == 200
    assert b'2 added to your Google Calendar' in r.data
    assert len(calls) == 2
    assert calls[0]['summary'].startswith('Senior Check-in: ') and 'Vega' in calls[0]['summary']
    assert calls[0]['start'].strftime('%Y-%m-%d %H:%M') == f'{TOMORROW} 09:00'
    assert calls[0]['end'].strftime('%H:%M') == '09:30'
    assert calls[0]['attendees'] is None and calls[0]['send_updates'] == 'none'
    assert 'Bring transcript' in calls[0]['description']
    with app.app_context():
        got = {b.student_id: b.google_event_id
               for b in Booking.query.filter_by(counselor_id=ids['me']).all()}
        assert got == {ids['a']: 'evt-1', ids['b']: 'evt-2'}


def test_confirm_without_the_box_leaves_google_alone(app, gcal_env):
    client, ids, calls = gcal_env
    _set_proposal(client, _individual_proposal(ids))
    r = _confirm(client)
    assert r.status_code == 200 and not calls
    with app.app_context():
        bookings = Booking.query.filter_by(counselor_id=ids['me']).all()
        assert len(bookings) == 2 and all(b.google_event_id is None for b in bookings)


def test_confirm_when_not_connected_saves_locally_and_says_so(app, gcal_env, monkeypatch):
    client, ids, calls = gcal_env
    monkeypatch.setattr(av.google_client, 'is_connected', lambda user: False)
    _set_proposal(client, _individual_proposal(ids))
    r = _confirm(client, add_to_google='1')
    assert not calls
    assert b'Google Calendar is not connected' in r.data
    with app.app_context():
        assert Booking.query.filter_by(counselor_id=ids['me']).count() == 2


def test_invites_go_only_to_students_with_an_email(app, gcal_env):
    client, ids, calls = gcal_env
    _set_proposal(client, _individual_proposal(ids))
    _confirm(client, add_to_google='1', invite_students='1')
    ana = next(c for c in calls if 'Vega' in c['summary'])
    luis = next(c for c in calls if 'Ybarra' in c['summary'])
    assert ana['attendees'] == ['ana@example.org'] and ana['send_updates'] == 'all'
    assert luis['attendees'] is None and luis['send_updates'] == 'none'


def test_group_meeting_is_one_google_event(app, gcal_env):
    client, ids, calls = gcal_env
    _set_proposal(client, {
        'mode': 'group', 'title': 'Senior Cohort', 'notes': '', 'duration': 45,
        'days_ahead': 14, 'meeting_type': 'general',
        'items': [{'student_ids': [ids['a'], ids['b']],
                   'student_names': ['Ana Vega', 'Luis Ybarra'],
                   'date': TOMORROW, 'day_name': 'Day', 'start_time': '10:00',
                   'end_time': '10:45', 'display': 'x'}],
        'unscheduled': [], 'created_at': 'x',
    })
    r = _confirm(client, add_to_google='1')
    assert b'1 added to your Google Calendar' in r.data
    assert len(calls) == 1 and calls[0]['summary'] == 'Senior Cohort'
    assert 'Ana Vega' in calls[0]['description']
    with app.app_context():
        ev = CalendarEvent.query.filter_by(owner_id=ids['me']).first()
        assert ev is not None and ev.google_event_id == 'evt-1'
        # Member bookings carry no event id: cancelling one student's booking
        # must not delete the whole group's Google event.
        assert all(b.google_event_id is None
                   for b in Booking.query.filter_by(counselor_id=ids['me']).all())


def test_catch_up_pushes_only_what_is_missing(app, gcal_env):
    client, ids, calls = gcal_env
    with app.app_context():
        def mk(sid, start, **kw):
            fields = dict(
                counselor_id=ids['me'], student_id=sid, booker_name='x',
                booker_relationship='counselor', student_name='Ana Vega',
                meeting_type='academic',
                appointment_date=date.today() + timedelta(days=2),
                start_time=start, end_time='09:30', status='confirmed')
            fields.update(kw)
            db.session.add(Booking(**fields))
        mk(ids['a'], '08:00')                                   # needs pushing
        mk(ids['b'], '09:00', google_event_id='already-there')  # done
        mk(ids['b'], '10:00', notes='(Part of group: Cohort)')  # group member
        mk(ids['a'], '11:00', status='cancelled')               # cancelled
        db.session.commit()
    r = client.post('/scheduling/api/bookings/push-google', json={})
    assert r.status_code == 200
    assert r.get_json() == {'ok': True, 'pushed': 1, 'failed': 0, 'skipped_group': 1}
    assert len(calls) == 1 and calls[0]['summary'] == 'Academic Concern: Ana Vega'
    with app.app_context():
        pushed = Booking.query.filter_by(counselor_id=ids['me'], start_time='08:00').first()
        assert pushed.google_event_id == 'evt-1'


def test_catch_up_requires_a_google_connection(app, gcal_env, monkeypatch):
    client, ids, calls = gcal_env
    monkeypatch.setattr(av.google_client, 'is_connected', lambda user: False)
    r = client.post('/scheduling/api/bookings/push-google', json={})
    assert r.status_code == 400 and not calls


def test_google_failure_keeps_the_appointment_and_reports_it(app, gcal_env, monkeypatch):
    client, ids, calls = gcal_env
    monkeypatch.setattr(av.google_calendar, 'create_event', lambda *a, **k: None)
    _set_proposal(client, _individual_proposal(ids))
    r = _confirm(client, add_to_google='1')
    assert b'0 added to your Google Calendar' in r.data
    assert b'2 could not be added' in r.data
    with app.app_context():
        bookings = Booking.query.filter_by(counselor_id=ids['me']).all()
        assert len(bookings) == 2 and all(b.google_event_id is None for b in bookings)
