"""First-run setup wizard: account-takeover regression + source hardening.

The bug this pins down: `/setup` guarded on
`not needs_setup() and current_user.is_authenticated`, so an ANONYMOUS caller
failed the second clause, fell through to _handle_complete(), and rewrote
User.query.first()'s username and password — a full account takeover from any
host that could reach the port. CSRF was no obstacle (the attacker GETs the
page first and gets a token bound to their own session).

Also covers the first-run window hardening: the wizard is necessarily anonymous,
so it only accepts requests from loopback unless explicitly opted out.
"""
import pytest

from app import db
from app.models.user import User
from app.routes.setup import SETUP_GRANT_KEY

REMOTE = {'REMOTE_ADDR': '100.64.0.9'}   # a tailnet peer — not loopback


@pytest.fixture
def primary_user(app):
    """The account an attacker would take over: User.query.first()."""
    with app.app_context():
        return User.query.order_by(User.id).first().id


@pytest.fixture
def pre_setup(app, primary_user):
    """Temporarily put the app back into the first-run state, then restore.

    Must restore, or every later test in the shared session DB starts getting
    redirected to the wizard by the global check_setup guard.
    """
    with app.app_context():
        user = db.session.get(User, primary_user)
        original = user.setup_completed
        user.setup_completed = False
        db.session.commit()
    yield
    with app.app_context():
        user = db.session.get(User, primary_user)
        user.setup_completed = original
        db.session.commit()


def _creds(app, uid):
    with app.app_context():
        u = db.session.get(User, uid)
        return u.username, u.password_hash


# ---------------------------------------------------- the takeover regression

def test_anonymous_post_cannot_take_over_account(app, client, primary_user):
    """THE exploit. Anonymous POST must not rewrite the counselor's login."""
    before = _creds(app, primary_user)

    r = client.post('/setup', data={
        'step': 'complete',
        'username': 'attacker',
        'password': 'attackerpassword123',
        'display_name': 'Attacker',
    })

    assert r.status_code == 404
    assert _creds(app, primary_user) == before, 'credentials were modified!'


def test_anonymous_get_is_404_after_setup(client):
    assert client.get('/setup').status_code == 404


def test_authenticated_get_still_redirects_to_dashboard(auth_client):
    """Post-setup UX for the counselor is unchanged."""
    r = auth_client.get('/setup')
    assert r.status_code == 302
    assert '/setup' not in r.headers['Location']


def test_setup_subroutes_closed_after_setup(client):
    for path in ('/setup/import-preview', '/setup/import-students', '/setup/upload-logo'):
        assert client.post(path).status_code == 404, path


# ------------------------------------------------- first-run window hardening

def test_wizard_renders_from_loopback_during_first_run(client, pre_setup):
    """The legitimate flow — including the post-factory-reset redirect, which
    arrives anonymous because factory_reset() calls logout_user()."""
    r = client.get('/setup')
    assert r.status_code == 200
    assert b'step' in r.data


def test_wizard_refused_from_remote_host_during_first_run(app, client, pre_setup,
                                                          primary_user):
    before = _creds(app, primary_user)
    r = client.get('/setup', environ_base=REMOTE)
    assert r.status_code == 403
    assert b'this computer' in r.data

    r = client.post('/setup', data={
        'step': 'complete', 'username': 'attacker',
        'password': 'attackerpassword123',
    }, environ_base=REMOTE)
    assert r.status_code == 403
    assert _creds(app, primary_user) == before


def test_remote_allowed_with_explicit_env_optin(client, pre_setup, monkeypatch):
    monkeypatch.setenv('COUNSELOR_ALLOW_REMOTE_SETUP', '1')
    assert client.get('/setup', environ_base=REMOTE).status_code == 200


def test_remote_allowed_with_factory_reset_grant(app, pre_setup):
    """A counselor who reset from their phone must be able to finish setup."""
    c = app.test_client()
    with c.session_transaction() as sess:
        sess[SETUP_GRANT_KEY] = True
    assert c.get('/setup', environ_base=REMOTE).status_code == 200


def test_grant_does_not_reopen_setup_once_complete(app):
    """The grant relaxes the SOURCE check only — never the needs_setup() gate."""
    c = app.test_client()
    with c.session_transaction() as sess:
        sess[SETUP_GRANT_KEY] = True
    assert c.get('/setup', environ_base=REMOTE).status_code == 404
