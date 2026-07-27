"""Public post-grad self-report survey link.

Covers: token-only student resolution (student_id can never be spoofed from
the form), 404 (not 403) on a bad token, ownership enforcement on the
authenticated edit/delete/survey-link routes, idempotent create-then-update
on repeat submissions, invalid-pathway rejection, the no-counselor edge case,
and that the pre-existing authenticated CRUD flow still works.
"""
import pytest

from app import db
from app.models.post_grad import PostGradOutcome
from app.models.student import Student
from app.models.user import User


@pytest.fixture
def pg_env(app):
    """Two counselors, one student each, for ownership/IDOR checks."""
    with app.app_context():
        me = User(username='pg_me', display_name='PG Me', role='counselor',
                  setup_completed=True)
        me.set_password('passw0rd123')
        other = User(username='pg_other', display_name='PG Other',
                     role='counselor', setup_completed=True)
        other.set_password('passw0rd123')
        db.session.add_all([me, other])
        db.session.commit()

        mine = Student(student_id_number='PG-MINE', first_name='Grady',
                        last_name='Mine', grade_level=12, status='graduated',
                        assigned_counselor_id=me.id, email='grady@example.com')
        theirs = Student(student_id_number='PG-THEIRS', first_name='Other',
                          last_name='Theirs', grade_level=12, status='graduated',
                          assigned_counselor_id=other.id)
        db.session.add_all([mine, theirs])
        db.session.commit()
        ids = dict(me=me.id, other=other.id, mine=mine.id, theirs=theirs.id)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(ids['me'])
        sess['_fresh'] = True

    yield client, ids

    with app.app_context():
        PostGradOutcome.query.filter(
            PostGradOutcome.student_id.in_([ids['mine'], ids['theirs']])
        ).delete(synchronize_session=False)
        Student.query.filter(Student.id.in_([ids['mine'], ids['theirs']])).delete(
            synchronize_session=False)
        User.query.filter(User.id.in_([ids['me'], ids['other']])).delete(
            synchronize_session=False)
        db.session.commit()


def _token(app, student_id):
    with app.app_context():
        s = db.session.get(Student, student_id)
        return s.get_or_create_postgrad_token()


# ---------------------------------------------------------------- public GET

def test_public_survey_valid_token_shows_form(app, pg_env):
    client, ids = pg_env
    token = _token(app, ids['mine'])
    r = client.get(f'/post-grad/survey/{token}')
    assert r.status_code == 200
    assert b'Grady' in r.data


def test_public_survey_invalid_token_404(app, pg_env):
    client, ids = pg_env
    r = client.get('/post-grad/survey/not-a-real-token')
    assert r.status_code == 404


def test_public_survey_token_stable_across_calls(app, pg_env):
    """The link must not rotate — a counselor may have already sent it out."""
    client, ids = pg_env
    t1 = _token(app, ids['mine'])
    t2 = _token(app, ids['mine'])
    assert t1 == t2


# --------------------------------------------------------------- public POST

def test_public_survey_submit_creates_outcome(app, pg_env):
    client, ids = pg_env
    token = _token(app, ids['mine'])
    r = client.post(f'/post-grad/survey/{token}', data={
        'primary_pathway': '4year_college',
        'graduation_year': '2026',
        'institution_name': 'State University',
        'contact_email': 'grady@example.com',
    })
    assert r.status_code == 200
    assert b'all set' in r.data.lower()

    with app.app_context():
        outcome = PostGradOutcome.query.filter_by(student_id=ids['mine']).first()
        assert outcome is not None
        assert outcome.counselor_id == ids['me']
        assert outcome.primary_pathway == '4year_college'
        assert outcome.institution_name == 'State University'


def test_public_survey_submit_cannot_spoof_other_student(app, pg_env):
    """A submitted student_id in the form body must be ignored entirely —
    the token is the only valid identity source."""
    client, ids = pg_env
    token = _token(app, ids['mine'])
    r = client.post(f'/post-grad/survey/{token}', data={
        'student_id': str(ids['theirs']),
        'primary_pathway': 'workforce',
    })
    assert r.status_code == 200

    with app.app_context():
        assert PostGradOutcome.query.filter_by(student_id=ids['theirs']).first() is None
        mine_outcome = PostGradOutcome.query.filter_by(student_id=ids['mine']).first()
        assert mine_outcome is not None
        assert mine_outcome.primary_pathway == 'workforce'


def test_public_survey_submit_invalid_pathway_rejected(app, pg_env):
    client, ids = pg_env
    token = _token(app, ids['mine'])
    r = client.post(f'/post-grad/survey/{token}', data={'primary_pathway': 'not-a-real-pathway'})
    assert r.status_code == 400
    with app.app_context():
        assert PostGradOutcome.query.filter_by(student_id=ids['mine']).first() is None


def test_public_survey_resubmit_updates_not_duplicates(app, pg_env):
    client, ids = pg_env
    token = _token(app, ids['mine'])
    client.post(f'/post-grad/survey/{token}', data={
        'primary_pathway': '4year_college', 'institution_name': 'First U',
    })
    client.post(f'/post-grad/survey/{token}', data={
        'primary_pathway': 'workforce', 'employer': 'Acme Co',
    })

    with app.app_context():
        outcomes = PostGradOutcome.query.filter_by(student_id=ids['mine']).all()
        assert len(outcomes) == 1
        assert outcomes[0].primary_pathway == 'workforce'
        assert outcomes[0].employer == 'Acme Co'


def test_public_survey_no_counselor_assigned(app, pg_env):
    client, ids = pg_env
    with app.app_context():
        s = db.session.get(Student, ids['mine'])
        s.assigned_counselor_id = None
        db.session.commit()
        token = s.get_or_create_postgrad_token()

    r = client.post(f'/post-grad/survey/{token}', data={'primary_pathway': '4year_college'})
    assert r.status_code == 400
    with app.app_context():
        assert PostGradOutcome.query.filter_by(student_id=ids['mine']).first() is None


# ------------------------------------------------------------ authenticated

def test_survey_link_requires_login(app, pg_env):
    _, ids = pg_env
    anon = app.test_client()
    r = anon.post(f'/post-grad/survey-link/{ids["mine"]}')
    assert r.status_code in (302, 401)


def test_survey_link_ownership_enforced(app, pg_env):
    """Counselor 'me' must not be able to mint a link for another counselor's
    student by guessing their numeric id."""
    client, ids = pg_env
    r = client.post(f'/post-grad/survey-link/{ids["theirs"]}')
    assert r.status_code == 404


def test_survey_link_returns_working_url(app, pg_env):
    client, ids = pg_env
    r = client.post(f'/post-grad/survey-link/{ids["mine"]}')
    assert r.status_code == 200
    payload = r.get_json()
    assert payload['ok'] is True
    assert '/post-grad/survey/' in payload['url']
    assert payload['student_email'] == 'grady@example.com'

    survey_path = payload['url'].split('/post-grad/', 1)[1]
    follow = client.get(f'/post-grad/{survey_path}')
    assert follow.status_code == 200


def test_edit_ownership_enforced(app, pg_env):
    client, ids = pg_env
    with app.app_context():
        theirs_outcome = PostGradOutcome(student_id=ids['theirs'],
                                          counselor_id=ids['other'],
                                          primary_pathway='4year_college')
        db.session.add(theirs_outcome)
        db.session.commit()
        outcome_id = theirs_outcome.id

    r = client.get(f'/post-grad/{outcome_id}/edit')
    assert r.status_code == 404


def test_edit_page_shows_survey_link_for_own_student(app, pg_env):
    client, ids = pg_env
    with app.app_context():
        outcome = PostGradOutcome(student_id=ids['mine'], counselor_id=ids['me'],
                                   primary_pathway='4year_college')
        db.session.add(outcome)
        db.session.commit()
        outcome_id = outcome.id

    r = client.get(f'/post-grad/{outcome_id}/edit')
    assert r.status_code == 200
    assert b'/post-grad/survey/' in r.data


def test_delete_ownership_enforced(app, pg_env):
    client, ids = pg_env
    with app.app_context():
        theirs_outcome = PostGradOutcome(student_id=ids['theirs'],
                                          counselor_id=ids['other'],
                                          primary_pathway='4year_college')
        db.session.add(theirs_outcome)
        db.session.commit()
        outcome_id = theirs_outcome.id

    r = client.post(f'/post-grad/{outcome_id}/delete')
    assert r.status_code == 404
    with app.app_context():
        assert db.session.get(PostGradOutcome, outcome_id) is not None


def test_index_lists_grad_without_outcome_links(app, pg_env):
    client, ids = pg_env
    r = client.get('/post-grad/')
    assert r.status_code == 200
    assert b'Grady' in r.data
    assert b'/post-grad/survey/' in r.data


def test_legacy_add_flow_still_works(app, pg_env):
    """The pre-existing authenticated manual-entry path is unaffected."""
    client, ids = pg_env
    r = client.post('/post-grad/add', data={
        'student_id': str(ids['mine']),
        'primary_pathway': '4year_college',
        'graduation_year': '2026',
    }, follow_redirects=True)
    assert r.status_code == 200

    with app.app_context():
        outcome = PostGradOutcome.query.filter_by(student_id=ids['mine']).first()
        assert outcome is not None
        assert outcome.counselor_id == ids['me']
