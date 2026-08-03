"""Whose theme wins: the signed-in user's saved preference, or this browser's.

The bug: a browser with no stored preference — a new machine, a cleared
profile, a private window — was forced to 'light' even though the server had
rendered the user's real theme, so the page visibly flashed from the correct
theme to the wrong one and stayed there.

The rule now: a saved preference from the database outranks localStorage.
localStorage still wins where there is no signed-in user (login, setup, public
forms), and is kept in sync so those pages inherit the last known choice.
"""
import re
from pathlib import Path

import pytest

from app import db
from app.models.user import User

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / 'app' / 'static' / 'js' / 'theme-manager.js'
BASE = ROOT / 'app' / 'templates' / 'base.html'


@pytest.fixture
def themed_user(app):
    with app.app_context():
        User.query.filter_by(username='theme_me').delete(synchronize_session=False)
        db.session.commit()
        u = User(username='theme_me', display_name='Theme Me', role='counselor',
                 setup_completed=True, theme_preference='glass-emerald',
                 reduced_motion=True)
        u.set_password('passw0rd123')
        db.session.add(u)
        db.session.commit()
        uid = u.id

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(uid)
        sess['_fresh'] = True
    yield client, uid

    with app.app_context():
        User.query.filter_by(id=uid).delete(synchronize_session=False)
        db.session.commit()


# ── what the server renders ──

def _html_tag(markup):
    """The opening <html ...> tag only.

    The marker's NAME also appears inside the inline bootstrap script on every
    page, so a substring search over the whole document proves nothing.
    """
    m = re.search(r'<html\b[^>]*>', markup, re.S)
    assert m, 'no <html> tag'
    return m.group(0)


def test_a_signed_in_users_theme_is_rendered_and_marked_authoritative(app, themed_user):
    client, _ = themed_user
    tag = _html_tag(client.get('/caseload/').data.decode())
    assert 'data-theme="glass-emerald"' in tag
    assert 'data-theme-saved="1"' in tag, (
        'without this marker the client cannot tell a real preference from '
        'the anonymous default, and falls back to localStorage')


def test_the_saved_reduced_motion_setting_is_rendered_too(app, themed_user):
    client, _ = themed_user
    assert 'data-server-reduced-motion="true"' in _html_tag(
        client.get('/caseload/').data.decode())


def test_an_anonymous_page_is_not_marked_authoritative(app):
    """Otherwise the login page would override a theme this browser chose."""
    tag = _html_tag(app.test_client().get('/login').data.decode())
    assert 'data-theme-saved' not in tag


# ── the client-side precedence rules ──

@pytest.fixture(scope='module')
def js():
    return JS.read_text(encoding='utf-8')


def test_get_theme_no_longer_hardcodes_light(js):
    """`localStorage.getItem(...) || 'light'` was the whole bug: an empty
    store silently outvoted the server."""
    assert not re.search(r"getItem\(\s*'theme_preference'\s*\)\s*\|\|\s*'light'", js)


def test_get_theme_falls_back_to_the_rendered_attribute(js):
    body = re.search(r'function getTheme\(\)\s*\{(.*?)\n    \}', js, re.S)
    assert body, 'getTheme is gone'
    assert "getAttribute('data-theme')" in body.group(1)


def test_the_head_bootstrap_prefers_the_saved_preference():
    """The inline script in <head> runs before CSS, so it is what prevents a
    flash — the precedence rule has to live there too, not only in the JS."""
    head = BASE.read_text(encoding='utf-8')
    script = re.search(r"var serverSaved = .*?\}\)\(\);", head, re.S)
    assert script, 'the head bootstrap no longer resolves the saved preference'
    body = script.group(0)
    assert "data-theme-saved" in body
    assert "setItem('theme_preference'" in body, \
        'server value is not synced back to localStorage'
    # The saved branch must read the attribute, not the store.
    assert "getAttribute('data-theme')" in body


def test_storage_access_is_guarded(js):
    """localStorage throws outright in some private-browsing modes; a theme
    read must not take the page down."""
    assert 'function storageGet' in js and 'function storageSet' in js
    guarded = re.search(r'function storageGet\(key\)\s*\{(.*?)\}', js, re.S)
    assert 'try' in guarded.group(1)
    # Every remaining direct localStorage touch must be inside those helpers.
    outside = [m for m in re.finditer(r'localStorage\.(getItem|setItem)', js)
               if not re.search(r'function storage(Get|Set)\([^)]*\)\s*\{[^}]*$',
                                js[:m.start()], re.S)]
    assert not outside, 'unguarded localStorage access outside the helpers'


def test_reduced_motion_prefers_the_saved_setting(js):
    body = re.search(r'function getReducedMotion\(\)\s*\{(.*?)\n    \}', js, re.S)
    assert body and 'serverSaved()' in body.group(1)


def test_toggling_reduced_motion_updates_the_rendered_attribute(js):
    """getReducedMotion() reads that attribute first, so a stale one would
    make the toggle report the value from page load."""
    body = re.search(r'function setReducedMotion\(enabled\)\s*\{(.*?)\n    \}', js, re.S)
    assert body and 'data-server-reduced-motion' in body.group(1)
