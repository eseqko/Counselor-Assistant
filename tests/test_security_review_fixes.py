"""Regression tests for the 2026-08 security review fixes.

Each test pins one plugged leak so it can't silently drift back. They cover:
cross-caseload import writes, the shared Ollama-endpoint authz gate, the login
open-redirect guard, the meeting-note / document existence oracles, the OAuth
callback state check, the dashboard iCal SSRF re-validation, the public
post-grad survey PII leak, the search-result XSS escaping, and the JSON-sidecar
PII purge on user deletion.

Cleanup uses bulk ``.delete(synchronize_session=False)`` (not ORM
``db.session.delete``) to match the rest of the suite: the app/db fixtures are
session-scoped, and an ORM user-delete would cascade a NULL onto other tests'
ImportLog rows through the shared session.
"""
import json
import os
from datetime import date

import pytest

from app import db
from app.models.user import User
from app.models.student import Student

_USERNAMES = ['secfix_a', 'secfix_b', 'secfix_c', 'secfix_d', 'secfix_e',
              'secfix_f', 'secfix_g', 'secfix_h', 'secfix_pg']
_SIDS = ['SECFIX-A', 'SECFIX-B', 'SECFIX-SHADOW', 'SECFIX-DOC', 'SECFIX-PG',
         'SECFIX-XSS']


def _scrub():
    """Remove any rows this module creates, using bulk deletes (no ORM cascade)."""
    from app.models.meeting_note import MeetingNote
    from app.models.document import StudentDocument
    from app.models.post_grad import PostGradOutcome
    from app.models.note import Note
    ids = [u.id for u in User.query.filter(User.username.in_(_USERNAMES)).all()]
    sids = [s.id for s in Student.query.filter(
        Student.student_id_number.in_(_SIDS)).all()]
    if ids:
        MeetingNote.query.filter(MeetingNote.author_id.in_(ids)).delete(
            synchronize_session=False)
    if sids:
        StudentDocument.query.filter(StudentDocument.student_id.in_(sids)).delete(
            synchronize_session=False)
        PostGradOutcome.query.filter(PostGradOutcome.student_id.in_(sids)).delete(
            synchronize_session=False)
        Note.query.filter(Note.student_id.in_(sids)).delete(
            synchronize_session=False)
    Student.query.filter(Student.student_id_number.in_(_SIDS)).delete(
        synchronize_session=False)
    User.query.filter(User.username.in_(_USERNAMES)).delete(
        synchronize_session=False)
    db.session.commit()


@pytest.fixture(autouse=True)
def _isolated(app):
    """Roll back inherited pending session state (e.g. an importer test's
    uncommitted ImportLog) and scrub our own rows before and after each test."""
    with app.app_context():
        db.session.rollback()
        _scrub()
    yield
    with app.app_context():
        db.session.rollback()
        _scrub()


def _mk_user(username, role='counselor'):
    u = User(username=username, display_name=username.title(), role=role,
             setup_completed=True)
    u.set_password('passw0rd123')
    db.session.add(u)
    db.session.commit()
    return u


def _mk_student(counselor_id, sid, **attrs):
    s = Student(student_id_number=sid, first_name='Test', last_name='Student',
                grade_level=11, status='active', assigned_counselor_id=counselor_id)
    for k, v in attrs.items():
        setattr(s, k, v)
    db.session.add(s)
    db.session.commit()
    return s


# ── Open redirect (auth._is_safe_redirect) ─────────────────────────────────
def test_open_redirect_guard_rejects_backslash_and_scheme_relative():
    from app.routes.auth import _is_safe_redirect
    assert _is_safe_redirect('/dashboard') is True
    assert _is_safe_redirect('/caseload/12') is True
    for bad in ('', '//evil.com', '/\\evil.com', '\\/evil.com', '\\\\evil.com',
                'https://evil.com', 'http://evil.com', '//evil.com/path',
                'javascript:alert(1)'):
        assert _is_safe_redirect(bad) is False, f'should reject: {bad!r}'


# ── Import cross-caseload guard (caseload.importable_student_ids) ───────────
def test_importable_student_ids_excludes_other_counselors(app):
    from app.utils.caseload import importable_student_ids
    with app.app_context():
        a = _mk_user('secfix_a')
        b = _mk_user('secfix_b')
        sa = _mk_student(a.id, 'SECFIX-A')
        sb = _mk_student(b.id, 'SECFIX-B')
        shadow = _mk_student(None, 'SECFIX-SHADOW', is_shadow=True)

        ids_a = importable_student_ids(a)
        assert sa.id in ids_a          # own student
        assert shadow.id in ids_a      # unowned/shadow (school-wide compare)
        assert sb.id not in ids_a      # another counselor's student — excluded

        b.role = 'admin'               # admin bypass sees the whole table
        db.session.commit()
        assert sa.id in importable_student_ids(b)


# ── Shared Ollama endpoint authz (POST /ai/settings) ───────────────────────
def test_ai_settings_post_denied_for_non_admin_when_multiuser(app):
    with app.app_context():
        c = _mk_user('secfix_c')          # non-admin
        _mk_user('secfix_d')              # a second account → gate becomes real
        cid = c.id
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(cid)
        sess['_fresh'] = True
    r = client.post('/ai/settings', json={'base_url': 'http://10.0.0.9:11434',
                                          'model': 'gemma3:4b'})
    assert r.status_code == 403, f'non-admin should be blocked, got {r.status_code}'


# ── Meeting-note existence oracle (404, never 302) ─────────────────────────
def test_meeting_note_foreign_returns_404(app):
    if not any(r.endpoint == 'meeting_notes.view' for r in app.url_map.iter_rules()):
        pytest.skip('meeting_notes blueprint not registered')
    from app.models.meeting_note import MeetingNote
    with app.app_context():
        a = _mk_user('secfix_e')
        b = _mk_user('secfix_f')
        note = MeetingNote(author_id=a.id, title='Private SST', content='secret',
                           meeting_type='sst', meeting_date=date.today())
        db.session.add(note)
        db.session.commit()
        nid, bid = note.id, b.id
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(bid)
        sess['_fresh'] = True
    # Foreign note and a nonexistent id must be indistinguishable (both 404).
    assert client.get(f'/meeting-notes/{nid}').status_code == 404
    assert client.get('/meeting-notes/99999999').status_code == 404


# ── Document download existence oracle (404, never 403) ────────────────────
def test_document_download_foreign_returns_404(app):
    if not any(r.endpoint == 'documents.download' for r in app.url_map.iter_rules()):
        pytest.skip('documents blueprint not registered')
    from app.models.document import StudentDocument
    with app.app_context():
        a = _mk_user('secfix_g')
        b = _mk_user('secfix_h')
        s = _mk_student(a.id, 'SECFIX-DOC')
        doc = StudentDocument(student_id=s.id, counselor_id=a.id,
                              document_type='iep', title='IEP',
                              filename='x.pdf', original_filename='x.pdf')
        db.session.add(doc)
        db.session.commit()
        did, bid = doc.id, b.id
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(bid)
        sess['_fresh'] = True
    assert client.get(f'/documents/{did}/download').status_code == 404


# ── OAuth callback state validation ────────────────────────────────────────
def test_google_callback_rejects_missing_state(app):
    if not any(r.endpoint == 'google_auth.callback' for r in app.url_map.iter_rules()):
        pytest.skip('google_auth blueprint not registered')
    client = app.test_client()
    client.get('/demo-login')
    # No google_oauth_state was minted in this session, so the callback must
    # bail out (redirect) rather than exchanging the supplied code.
    r = client.get('/google/callback?state=attacker&code=abc123',
                   follow_redirects=False)
    assert r.status_code in (301, 302)
    assert '/google' not in r.headers.get('Location', '')  # not looping the callback


# ── Dashboard iCal SSRF re-validation ──────────────────────────────────────
def test_dashboard_external_events_blocks_internal_targets(app):
    from app.routes.dashboard import _fetch_todays_external_events

    class _U:
        def __init__(self, url):
            self.external_ical_url = url

    with app.app_context():
        assert _fetch_todays_external_events(_U(None)) == []
        assert _fetch_todays_external_events(_U('http://localhost:11434/x')) == []
        assert _fetch_todays_external_events(_U('http://127.0.0.1:8080/x')) == []
        assert _fetch_todays_external_events(_U('http://169.254.169.254/latest/')) == []


# ── Public post-grad survey must not leak counselor-internal notes ─────────
def test_post_grad_survey_hides_counselor_notes(app):
    if not any(r.endpoint == 'post_grad.public_survey' for r in app.url_map.iter_rules()):
        pytest.skip('post_grad blueprint not registered')
    from app.models.post_grad import PostGradOutcome
    with app.app_context():
        a = _mk_user('secfix_pg')
        s = _mk_student(a.id, 'SECFIX-PG')
        if hasattr(s, 'get_survey_token'):
            token = s.get_survey_token()
        else:
            import secrets
            s.postgrad_survey_token = secrets.token_urlsafe(32)
            token = s.postgrad_survey_token
        db.session.add(PostGradOutcome(
            student_id=s.id, counselor_id=a.id, primary_pathway='4year_college',
            notes='COUNSELOR_ONLY_SECRET', self_report_notes='STUDENT_WROTE_THIS'))
        db.session.commit()
    client = app.test_client()
    r = client.get(f'/post-grad/survey/{token}')
    assert r.status_code == 200
    assert 'COUNSELOR_ONLY_SECRET' not in r.get_data(as_text=True)  # plugged leak


# ── Global search escapes user data in the result subtitle ─────────────────
def test_search_subtitle_escapes_student_name(app):
    from app.models.note import Note
    client = app.test_client()
    client.get('/demo-login')
    with app.app_context():
        demo = User.query.filter_by(username='demo').first()
        s = _mk_student(demo.id, 'SECFIX-XSS',
                        last_name='<img src=x onerror=alert(1)>')
        note = Note(student_id=s.id, author_id=demo.id, note_type='academic',
                    title='ZZSEARCHPROBE', content='body')
        db.session.add(note)
        db.session.commit()
    r = client.get('/api/search?q=ZZSEARCHPROBE')
    assert r.status_code == 200
    note_hits = [x for x in r.get_json()['results'] if x['type'] == 'note']
    assert note_hits, 'probe note not returned by search'
    sub = note_hits[0]['subtitle']
    assert '<img' not in sub                      # raw markup must not appear
    assert '&lt;img' in sub                        # it is HTML-escaped


# ── JSON-sidecar PII purge on user deletion ────────────────────────────────
def test_purge_counselor_sidecars_removes_only_target(app):
    from config import DATA_DIR
    from app.utils.user_data import purge_counselor_sidecars
    path = os.path.join(DATA_DIR, 'followups.json')
    backup = None
    if os.path.exists(path):
        with open(path) as f:
            backup = f.read()
    try:
        with open(path, 'w') as f:
            json.dump([
                {'id': '1', 'counselor_id': 4242, 'student_name': 'Gone'},
                {'id': '2', 'counselor_id': 777, 'student_name': 'Kept'},
            ], f)
        removed = purge_counselor_sidecars(4242)
        with open(path) as f:
            data = json.load(f)
        assert removed == 1
        assert all(e['counselor_id'] != 4242 for e in data)
        assert any(e['counselor_id'] == 777 for e in data)
    finally:
        if backup is not None:
            with open(path, 'w') as f:
                f.write(backup)
        elif os.path.exists(path):
            os.remove(path)
