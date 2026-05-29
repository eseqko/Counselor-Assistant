"""Smoke sweep: no GET route should return a 5xx, and regression tests for
the two latent crash bugs fixed in this branch (ASCA create + course recs).

This is the cheap safety net that would have caught the missing-import and
undefined-name bugs automatically.
"""
import pytest

# Endpoints that make synchronous external calls (Google/OAuth live fetch) or
# are destructive / would end the session — excluded from the sweep.
SKIP_ENDPOINTS = {
    'google_auth.authorize', 'google_auth.callback',
    'calendar.get_external_events', 'calendar.get_google_events',
    'auth.logout',                 # would log the sweep client out
    'settings.factory_reset',      # destructive (also POST)
    'demo.reset',                  # wipes/reseeds demo data (POST)
    'demo.login',                  # re-login mid-sweep
}

# Param names that should be filled with a real seeded object id.
_REAL_ID_ARGS = {'student_id', 'note_id'}


def _seeded_ids(app):
    from app.models.student import Student
    from app.models.note import Note
    with app.app_context():
        s = Student.query.first()
        n = Note.query.first()
        return {'student': s.id if s else 1, 'note': n.id if n else 1}


def _fill(rule, ids):
    """Best-effort URL args. Real ids where we can map them; a non-existent id
    otherwise (route should 404 gracefully, never 500)."""
    out = {}
    bp = rule.endpoint.split('.')[0]
    for a in rule.arguments:
        if a == 'student_id':
            out[a] = ids['student']
        elif a == 'note_id':
            out[a] = ids['note']
        elif a == 'id':
            if bp in ('caseload', 'graduation', 'meeting_prep'):
                out[a] = ids['student']
            elif bp == 'notes':
                out[a] = ids['note']
            else:
                out[a] = 999999          # unknown -> expect graceful 404
        elif a in ('tid', 'tool_id', 'record_id', 'score_id', 'entry_id',
                   'doc_id', 'app_id'):
            out[a] = 999999
        else:                            # token / filename / path
            out[a] = 'nonexistent'
    return out


def _get_rules(app, with_args):
    rules = []
    for r in app.url_map.iter_rules():
        if r.endpoint == 'static' or 'GET' not in r.methods:
            continue
        if r.endpoint in SKIP_ENDPOINTS:
            continue
        if bool(r.arguments) == with_args:
            rules.append(r)
    return sorted(rules, key=lambda r: r.endpoint)


def test_zero_arg_get_routes_never_500(app, auth_client):
    failures = []
    for r in _get_rules(app, with_args=False):
        resp = auth_client.get(r.rule)
        if resp.status_code >= 500:
            failures.append(f'{r.endpoint} {r.rule} -> {resp.status_code}')
    assert not failures, 'Server errors on GET routes:\n' + '\n'.join(failures)


def _substitute(rule_str, values):
    url = rule_str
    for k, v in values.items():
        for conv in ('int:', 'path:', 'string:', ''):
            url = url.replace(f'<{conv}{k}>', str(v))
    return url


def test_param_get_routes_never_500(app, auth_client):
    ids = _seeded_ids(app)
    failures = []
    for r in _get_rules(app, with_args=True):
        url = _substitute(r.rule, _fill(r, ids))
        resp = auth_client.get(url)
        if resp.status_code >= 500:
            failures.append(f'{r.endpoint} {url} -> {resp.status_code}')
    assert not failures, 'Server errors on param GET routes:\n' + '\n'.join(failures)


# ---- regression tests for the two bugs fixed on this branch ---------------

def test_asca_program_create_redirects_not_500(auth_client):
    """reports.py was missing redirect/url_for -> this POST used to 500."""
    resp = auth_client.post('/reports/asca-results/add',
                            data={'name': 'Smoke Test Program'})
    assert resp.status_code in (302, 303), resp.status_code


def test_course_recommendations_no_crash(app, auth_client, make_student):
    """course_recommendations referenced undefined names -> used to 500."""
    sid = make_student(grade=10, completed=60, wip=15, quarter='10-Q3')
    # Ensure the catalog isn't empty so we reach the (previously broken) block.
    from app.models.course import Course, Department
    with app.app_context():
        from app import db
        if not Course.query.filter_by(is_active=True).first():
            d = Department(name='English')
            db.session.add(d)
            db.session.flush()
            for i in range(6):
                db.session.add(Course(
                    department_id=d.id, course_number=f'SMK{i}', title=f'Course {i}',
                    credits=5.0, is_active=True, subject_area='English',
                    grade_levels='9,10,11,12'))
            db.session.commit()
    resp = auth_client.post('/ai/course-recommendations', json={'student_id': sid})
    assert resp.status_code == 200, resp.status_code
    assert resp.get_json().get('recommendations')   # non-empty (AI-fallback ok)
