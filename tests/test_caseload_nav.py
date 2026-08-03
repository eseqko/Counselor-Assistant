"""Prev/next student navigation, and the filter that rides along with it.

The contract: the profile's prev/next must walk exactly the set the caseload
list is showing, in exactly the same order. If those two ever disagree, "Next"
can skip a student or bounce back to the one you just left — which is why the
filtering and ordering live in one shared helper rather than being duplicated.
"""
import re

import pytest

from app import db
from app.models.student import Student, Tag
from app.models.user import User
from app.routes.caseload import (
    active_filter_args, apply_caseload_filters, caseload_base_query,
    filtered_caseload_ids,
)


@pytest.fixture
def nav_env(app):
    """A caseload with a deliberate mix: two grades, an inactive student, an
    LTEL, a tagged student, a same-name pair (to exercise the id tiebreaker),
    a sample student, and another counselor's student.
    """
    with app.app_context():
        User.query.filter(User.username.in_(['nav_me', 'nav_other'])).delete(
            synchronize_session=False)
        Student.query.filter(Student.student_id_number.like('NAV-%')).delete(
            synchronize_session=False)
        db.session.commit()

        me = User(username='nav_me', display_name='Nav Me', role='counselor',
                  setup_completed=True)
        me.set_password('passw0rd123')
        other = User(username='nav_other', display_name='Nav Other',
                     role='counselor', setup_completed=True)
        other.set_password('passw0rd123')
        db.session.add_all([me, other])
        db.session.commit()

        # Tag.name is unique and tags outlive a student delete, so reuse any
        # left over from a prior run instead of colliding on insert.
        focus = Tag.query.filter_by(name='NavFocus').first()
        if focus is None:
            focus = Tag(name='NavFocus')
            db.session.add(focus)
            db.session.commit()
        # A bulk Student.delete() does NOT cascade to the student_tags
        # association table, and SQLite recycles rowids — so a new student can
        # inherit a dead student's id and collide with its orphaned tag row.
        db.session.execute(
            db.text('DELETE FROM student_tags WHERE tag_id = :tid'),
            {'tid': focus.id})
        db.session.commit()

        def student(num, last, first, **kw):
            kw.setdefault('grade_level', 11)
            kw.setdefault('status', 'active')
            s = Student(student_id_number=num, last_name=last, first_name=first,
                        assigned_counselor_id=me.id, **kw)
            db.session.add(s)
            return s

        # Alphabetical by (last, first): Alpha,Ann · Beta,Bob · Beta,Zoe ·
        # Gamma,Gil · Delta(inactive) · Echo(grade 12) · Sample
        a = student('NAV-1', 'Alpha', 'Ann', el_status='LTEL')
        b = student('NAV-2', 'Beta', 'Bob')
        b2 = student('NAV-3', 'Beta', 'Bob')          # same name -> id tiebreak
        g = student('NAV-4', 'Gamma', 'Gil', el_status='LTEL')
        inactive = student('NAV-5', 'Delta', 'Dee', status='inactive')
        grade12 = student('NAV-6', 'Echo', 'Eve', grade_level=12)
        sample = student('NAV-7', 'Aaa', 'Sample', is_sample=True)
        theirs = Student(student_id_number='NAV-9', last_name='Zulu',
                         first_name='Zed', grade_level=11, status='active',
                         assigned_counselor_id=other.id)
        db.session.add(theirs)
        db.session.commit()

        g.tags.append(focus)
        db.session.commit()

        ids = dict(me=me.id, other=other.id, a=a.id, b=b.id, b2=b2.id, g=g.id,
                   inactive=inactive.id, grade12=grade12.id, sample=sample.id,
                   theirs=theirs.id, tag=focus.id)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(ids['me'])
        sess['_fresh'] = True

    yield client, ids

    with app.app_context():
        Student.query.filter(Student.student_id_number.like('NAV-%')).delete(
            synchronize_session=False)
        Tag.query.filter_by(name='NavFocus').delete(synchronize_session=False)
        User.query.filter(User.id.in_([ids['me'], ids['other']])).delete(
            synchronize_session=False)
        db.session.commit()


def _user(app, uid):
    return db.session.get(User, uid)


# ── the ordered, filtered id list ──

def test_default_view_is_active_students_in_name_order(app, nav_env):
    _, ids = nav_env
    with app.app_context():
        got = filtered_caseload_ids(_user(app, ids['me']), {})
    assert got == [ids['a'], ids['b'], ids['b2'], ids['grade12'], ids['g']]


def test_same_name_students_order_deterministically_by_id(app, nav_env):
    """Without an id tiebreaker these two could swap between queries, so the
    list and prev/next would disagree about which comes first."""
    _, ids = nav_env
    with app.app_context():
        user = _user(app, ids['me'])
        first = filtered_caseload_ids(user, {})
        second = filtered_caseload_ids(user, {})
    assert first == second
    assert first.index(ids['b']) < first.index(ids['b2'])


def test_sample_student_and_other_counselors_are_excluded(app, nav_env):
    _, ids = nav_env
    with app.app_context():
        got = filtered_caseload_ids(_user(app, ids['me']), {})
    assert ids['sample'] not in got
    assert ids['theirs'] not in got


def test_status_filter(app, nav_env):
    _, ids = nav_env
    with app.app_context():
        got = filtered_caseload_ids(_user(app, ids['me']), {'status': 'inactive'})
    assert got == [ids['inactive']]


def test_grade_filter(app, nav_env):
    _, ids = nav_env
    with app.app_context():
        got = filtered_caseload_ids(_user(app, ids['me']), {'grade': '12'})
    assert got == [ids['grade12']]


def test_el_status_filter(app, nav_env):
    _, ids = nav_env
    with app.app_context():
        got = filtered_caseload_ids(_user(app, ids['me']), {'el_status': 'LTEL'})
    assert got == [ids['a'], ids['g']]


def test_tag_filter(app, nav_env):
    _, ids = nav_env
    with app.app_context():
        got = filtered_caseload_ids(_user(app, ids['me']), {'tag': 'NavFocus'})
    assert got == [ids['g']]


def test_search_matches_name_or_student_id(app, nav_env):
    _, ids = nav_env
    with app.app_context():
        user = _user(app, ids['me'])
        assert filtered_caseload_ids(user, {'search': 'Alpha'}) == [ids['a']]
        assert filtered_caseload_ids(user, {'search': 'NAV-4'}) == [ids['g']]


def test_non_numeric_grade_is_ignored_rather_than_crashing(app, nav_env):
    """?grade=x used to raise ValueError from int() and 500 the page."""
    _, ids = nav_env
    with app.app_context():
        got = filtered_caseload_ids(_user(app, ids['me']), {'grade': 'notanumber'})
    assert len(got) == 5


def test_list_and_nav_agree_on_membership_and_order(app, nav_env):
    """The whole point of the shared helper."""
    client, ids = nav_env
    r = client.get('/caseload/?el_status=LTEL')
    assert r.status_code == 200
    html = r.data.decode()
    rendered = [int(m) for m in re.findall(r'/caseload/(\d+)\?', html)]
    seen = list(dict.fromkeys(rendered))

    with app.app_context():
        expected = filtered_caseload_ids(_user(app, ids['me']), {'el_status': 'LTEL'})
    assert seen == expected


# ── filter round-trip into links ──

def test_active_filter_args_keeps_only_present_keys():
    args = {'grade': '11', 'status': 'active', 'search': '', 'page': '3'}
    assert active_filter_args(args) == {'grade': '11', 'status': 'active'}


def test_list_links_carry_the_filter(app, nav_env):
    client, ids = nav_env
    html = client.get('/caseload/?grade=11&el_status=LTEL').data.decode()
    assert f'/caseload/{ids["a"]}?' in html
    link = re.search(rf'/caseload/{ids["a"]}\?[^"\']+', html).group(0)
    assert 'grade=11' in link and 'el_status=LTEL' in link


def test_page_is_not_carried_into_the_profile_link(app, nav_env):
    """The profile navigates by position, so a stale page number is noise."""
    client, ids = nav_env
    html = client.get('/caseload/?grade=11&page=1').data.decode()
    link = re.search(rf'/caseload/{ids["a"]}\?[^"\']+', html).group(0)
    assert 'page=' not in link


# ── prev/next on the profile ──

def test_prev_and_next_walk_the_filtered_set(app, nav_env):
    """Grade 11 / LTEL is Alpha then Gamma — Next from Alpha must skip the
    non-LTEL students in between."""
    client, ids = nav_env
    html = client.get(f'/caseload/{ids["a"]}?el_status=LTEL').data.decode()
    nav = re.search(r'id="student-nav-next"[^>]*href="([^"]+)"', html)
    assert nav, 'no Next link rendered'
    assert f'/caseload/{ids["g"]}' in nav.group(1)
    assert 'el_status=LTEL' in nav.group(1)


def test_the_ends_wrap_around(app, nav_env):
    """Grade 11 / LTEL is Alpha then Gamma. Prev from the first must land on
    the last and Next from the last on the first — carrying the filter, so the
    wrap stays inside the set the counselor is working."""
    client, ids = nav_env

    first = client.get(f'/caseload/{ids["a"]}?el_status=LTEL').data.decode()
    prev = re.search(r'id="student-nav-prev"[^>]*href="([^"]+)"', first)
    assert prev, 'first student has no Prev link — the ends did not wrap'
    assert f'/caseload/{ids["g"]}' in prev.group(1)
    assert 'el_status=LTEL' in prev.group(1)

    last = client.get(f'/caseload/{ids["g"]}?el_status=LTEL').data.decode()
    nxt = re.search(r'id="student-nav-next"[^>]*href="([^"]+)"', last)
    assert nxt, 'last student has no Next link — the ends did not wrap'
    assert f'/caseload/{ids["a"]}' in nxt.group(1)
    assert 'el_status=LTEL' in nxt.group(1)


def test_a_single_student_caseload_renders_no_nav_links(app, nav_env):
    """Wrapping a one-student list would point both buttons at the page you're
    already on. Nothing to walk to means no buttons."""
    client, ids = nav_env
    # Grade 12 has exactly one student, so the filtered set has length 1.
    html = client.get(f'/caseload/{ids["grade12"]}?grade=12').data.decode()
    assert '1 of 1' in html, 'fixture no longer isolates a single student'
    assert 'id="student-nav-prev"' not in html
    assert 'id="student-nav-next"' not in html


def test_position_counter_reflects_the_filtered_set(app, nav_env):
    client, ids = nav_env
    html = client.get(f'/caseload/{ids["g"]}?el_status=LTEL').data.decode()
    assert '2 of 2' in html


def test_counter_is_hidden_when_the_student_is_outside_the_filter(app, nav_env):
    """A grade-12 student reached with ?grade=11 isn't part of that set, so
    claiming a position in it would be a lie."""
    client, ids = nav_env
    html = client.get(f'/caseload/{ids["grade12"]}?grade=11').data.decode()
    assert ' of ' not in html.split('student-nav')[1][:400]


def test_out_of_filter_student_still_gets_working_navigation(app, nav_env):
    """Never a dead end: fall back to the unfiltered caseload."""
    client, ids = nav_env
    html = client.get(f'/caseload/{ids["grade12"]}?grade=11').data.decode()
    assert ('id="student-nav-prev"' in html or 'id="student-nav-next"' in html)
    # And the stale filter is dropped rather than propagated.
    nav = re.search(r'id="student-nav-(?:prev|next)"[^>]*href="([^"]+)"', html)
    assert 'grade=11' not in nav.group(1)


def test_navigation_never_leaves_the_users_own_caseload(app, nav_env):
    """Every id offered by prev/next must belong to the requester."""
    client, ids = nav_env
    with app.app_context():
        mine = set(filtered_caseload_ids(_user(app, ids['me']), {}))
    for sid in (ids['a'], ids['b'], ids['b2'], ids['g'], ids['grade12']):
        html = client.get(f'/caseload/{sid}').data.decode()
        for href in re.findall(r'id="student-nav-(?:prev|next)"[^>]*href="([^"]+)"', html):
            target = int(re.search(r'/caseload/(\d+)', href).group(1))
            assert target in mine
            assert target != ids['theirs']


def test_a_tampered_filter_cannot_reach_another_counselors_student(app, nav_env):
    """Filter values are attacker-controllable; the caseload scope is not."""
    client, ids = nav_env
    with app.app_context():
        got = filtered_caseload_ids(_user(app, ids['me']),
                                    {'search': 'Zulu', 'status': 'active'})
    assert got == []
    assert client.get(f'/caseload/{ids["theirs"]}').status_code == 404


def test_profile_survives_a_junk_grade_filter(app, nav_env):
    client, ids = nav_env
    assert client.get(f'/caseload/{ids["a"]}?grade=notanumber').status_code == 200
    assert client.get('/caseload/?grade=notanumber').status_code == 200


def test_walking_next_laps_the_caseload_exactly_once(app, nav_env):
    """End-to-end: follow Next from the first student for exactly one lap. The
    walk must reproduce the list order without repeats or skips, then close the
    loop by returning to where it started."""
    client, ids = nav_env
    with app.app_context():
        expected = filtered_caseload_ids(_user(app, ids['me']), {})
    assert len(expected) > 1, 'fixture needs a walkable caseload'

    visited = [expected[0]]
    url = f'/caseload/{expected[0]}'
    for _ in range(len(expected)):            # one full lap, then stop
        html = client.get(url).data.decode()
        nav = re.search(r'id="student-nav-next"[^>]*href="([^"]+)"', html)
        assert nav, f'Next vanished mid-walk at {url}'
        url = nav.group(1).replace('&amp;', '&')
        visited.append(int(re.search(r'/caseload/(\d+)', url).group(1)))

    assert visited[:-1] == expected, 'walk did not reproduce the list order'
    assert visited[-1] == expected[0], 'the lap did not wrap back to the start'
