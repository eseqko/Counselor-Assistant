"""Unit tests for the consolidated school-identity store (app/utils/school_config).

These guard the merge semantics that fixed the Catalog-Wiki-vs-main-app drift:
a save from one surface must never drop fields owned by another, and the
school_name column must stay synced with schoolName. Pure in-memory (commit=False)
so no DB/app-context is needed.
"""
import json

import pytest

from app.models.user import User
from app.utils.school_config import get_school_config, merge_school_config


@pytest.fixture(autouse=True)
def _models_ready(app):
    """Depend on the session app fixture so create_app() has run and all
    SQLAlchemy mappers are configured before we instantiate User()."""
    return app


def _user(**kw):
    u = User(username='t', display_name='t', role='counselor')
    for k, v in kw.items():
        setattr(u, k, v)
    return u


def test_get_backfills_name_from_column():
    u = _user(school_name='Lincoln High',
              school_config_json=json.dumps({'colors': {'primary': '#111'}}))
    cfg = get_school_config(u)
    assert cfg['schoolName'] == 'Lincoln High'
    assert cfg['colors']['primary'] == '#111'


def test_get_tolerates_bad_or_missing_json():
    assert get_school_config(_user(school_name='X', school_config_json='not json{')) == {'schoolName': 'X'}
    assert get_school_config(_user(school_name='', school_config_json=None)) == {}


def test_merge_preserves_absent_keys():
    """The core fix: a Catalog-Wiki-style save (no grade_levels/counselor_title)
    must not drop those main-app-owned fields."""
    u = _user(school_name='Lincoln', school_config_json=json.dumps({
        'schoolName': 'Lincoln', 'grade_levels': ['9', '10'], 'counselor_title': 'C'}))
    merge_school_config(u, {'mascot': 'Lions', 'schoolName': 'Lincoln'}, commit=False)
    cfg = get_school_config(u)
    assert cfg['grade_levels'] == ['9', '10']   # preserved
    assert cfg['counselor_title'] == 'C'        # preserved
    assert cfg['mascot'] == 'Lions'             # added


def test_merge_syncs_school_name_column():
    u = _user(school_name='Old', school_config_json='{}')
    merge_school_config(u, {'schoolName': 'New High'}, commit=False)
    assert u.school_name == 'New High'
    assert get_school_config(u)['schoolName'] == 'New High'


def test_colors_submerge_keeps_other_channel():
    u = _user(school_config_json=json.dumps({'colors': {'primary': '#1', 'secondary': '#2'}}))
    merge_school_config(u, {'colors': {'primary': '#9'}}, commit=False)
    assert get_school_config(u)['colors'] == {'primary': '#9', 'secondary': '#2'}


def test_empty_colour_does_not_wipe_existing():
    u = _user(school_config_json=json.dumps({'colors': {'primary': '#1', 'secondary': '#2'}}))
    merge_school_config(u, {'colors': {'primary': ''}}, commit=False)
    assert get_school_config(u)['colors'] == {'primary': '#1', 'secondary': '#2'}


def test_present_empty_clears_owned_field():
    """Logo removal (and other intentional clears) set the field to '' — a
    present empty value should win so the clear persists."""
    u = _user(school_config_json=json.dumps({'logoUrl': 'http://x/logo.png'}))
    merge_school_config(u, {'logoUrl': ''}, commit=False)
    assert get_school_config(u).get('logoUrl') == ''


def test_setup_complete_derived_from_name_and_colour():
    """The in-app Course Catalog iframe gates on setupComplete: a user who set
    school identity via the main-app wizard / profile (which never write the
    flag) must still be treated as 'configured' so the iframe renders the
    catalog instead of bouncing back to setup."""
    u = _user(school_name='Lincoln',
              school_config_json=json.dumps({
                  'schoolName': 'Lincoln', 'colors': {'primary': '#111'}}))
    assert get_school_config(u).get('setupComplete') is True


def test_setup_complete_not_derived_without_colour():
    u = _user(school_name='Lincoln',
              school_config_json=json.dumps({'schoolName': 'Lincoln'}))
    assert 'setupComplete' not in get_school_config(u)


def test_explicit_setup_complete_false_is_preserved():
    """A user who intentionally reset setup (setupComplete: False) must NOT be
    auto-promoted by the derivation."""
    u = _user(school_name='Lincoln',
              school_config_json=json.dumps({
                  'schoolName': 'Lincoln',
                  'colors': {'primary': '#111'},
                  'setupComplete': False}))
    assert get_school_config(u).get('setupComplete') is False
