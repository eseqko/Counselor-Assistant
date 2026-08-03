"""Splitting the one overloaded token into three per-surface tokens.

calendar_feed_token gated the student portal, the public booking page AND the
private iCal feed. The portal link is meant to be broadcast to a whole
caseload, so any student holding it could swap the URL path and read the
counselor's calendar — student names and free-text appointment notes included.

The migration must preserve the two links already in families' hands while
re-issuing the one that leaked.
"""
import pytest

from app import db, _split_feed_tokens
from app.models.user import User


@pytest.fixture
def legacy_user(app):
    """A user as they existed before the split: one token, three surfaces."""
    with app.app_context():
        u = User(username='legacy_tok', display_name='Legacy', role='counselor',
                 setup_completed=True)
        u.set_password('passw0rd123')
        u.calendar_feed_token = 'LEGACY-TOKEN-IN-STUDENT-HANDS'
        u.portal_token = None
        u.booking_token = None
        u.ical_feed_token = None
        db.session.add(u)
        db.session.commit()
        uid = u.id
    yield uid
    with app.app_context():
        User.query.filter_by(id=uid).delete()
        db.session.commit()


def test_migration_preserves_portal_and_booking_links(app, legacy_user):
    """Links already sent to families must keep working."""
    with app.app_context():
        _split_feed_tokens(app)
        u = db.session.get(User, legacy_user)
        assert u.portal_token == 'LEGACY-TOKEN-IN-STUDENT-HANDS'
        assert u.booking_token == 'LEGACY-TOKEN-IN-STUDENT-HANDS'


def test_migration_reissues_the_ical_token(app, legacy_user):
    """THE point of the split: the token students hold must stop opening the
    private calendar. Carrying it over would migrate the leak, not close it."""
    with app.app_context():
        _split_feed_tokens(app)
        u = db.session.get(User, legacy_user)
        assert u.ical_feed_token != 'LEGACY-TOKEN-IN-STUDENT-HANDS'
        assert u.ical_feed_token
        assert len(u.ical_feed_token) >= 40


def test_migration_is_idempotent(app, legacy_user):
    with app.app_context():
        _split_feed_tokens(app)
        first = db.session.get(User, legacy_user).ical_feed_token
        _split_feed_tokens(app)
        assert db.session.get(User, legacy_user).ical_feed_token == first


def test_portal_token_cannot_open_the_calendar_feed(app, legacy_user):
    """The exact cross-surface swap the review demonstrated."""
    with app.app_context():
        _split_feed_tokens(app)
        u = db.session.get(User, legacy_user)
        portal, ical = u.portal_token, u.ical_feed_token

    client = app.test_client()
    assert client.get(f'/calendar/feed/{portal}.ics').status_code == 404
    assert client.get(f'/calendar/feed/{ical}.ics').status_code == 200


def test_booking_token_cannot_open_the_calendar_feed(app, legacy_user):
    with app.app_context():
        _split_feed_tokens(app)
        booking = db.session.get(User, legacy_user).booking_token
    client = app.test_client()
    assert client.get(f'/calendar/feed/{booking}.ics').status_code == 404


def test_ical_token_cannot_open_the_student_portal(app, legacy_user):
    """Separation runs both ways — the private token shouldn't unlock the
    portal's unauthenticated LLM endpoints either."""
    with app.app_context():
        _split_feed_tokens(app)
        ical = db.session.get(User, legacy_user).ical_feed_token
    client = app.test_client()
    assert client.get(f'/student-portal/{ical}').status_code == 404


def test_each_surface_rotates_independently(app, legacy_user):
    """Revoking a leaked portal link must not kill the calendar subscription."""
    with app.app_context():
        _split_feed_tokens(app)
        u = db.session.get(User, legacy_user)
        before = (u.portal_token, u.booking_token, u.ical_feed_token)
        u.rotate_token('portal')
        u = db.session.get(User, legacy_user)
        after = (u.portal_token, u.booking_token, u.ical_feed_token)

    assert after[0] != before[0], 'portal token did not rotate'
    assert after[1] == before[1], 'booking token rotated as collateral'
    assert after[2] == before[2], 'calendar feed rotated as collateral'


def test_regenerate_route_requires_login_and_valid_surface(app, legacy_user):
    anon = app.test_client()
    assert anon.post('/settings/regenerate-token/portal').status_code in (302, 401)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(legacy_user)
        sess['_fresh'] = True
    assert client.post('/settings/regenerate-token/not-a-surface').status_code == 404
    assert client.post('/settings/regenerate-token/ical').status_code == 302


def test_new_users_get_three_distinct_tokens(app):
    with app.app_context():
        u = User(username='fresh_tok', display_name='Fresh', role='counselor')
        u.set_password('passw0rd123')
        db.session.add(u)
        db.session.commit()
        tokens = {u.get_or_create_portal_token(),
                  u.get_or_create_booking_token(),
                  u.get_or_create_ical_token()}
        uid = u.id
    assert len(tokens) == 3, 'a surface is reusing another surface\'s token'
    with app.app_context():
        User.query.filter_by(id=uid).delete()
        db.session.commit()
