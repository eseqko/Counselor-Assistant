"""Credit-pace benchmarks, recalibrated to the school's real earning capacity.

The bug this pins down: benchmarks assumed ~55 credits/year while JUHSD's
accelerated block earns 80 (4 classes x 4 quarters x 5 credits). A 9th grader
who had FAILED HALF their courses read as "on-track", and in grades 10-12 that
same student never got worse than "warning" — the flag under-warned on exactly
the students it exists to catch.

The old curve also expected only 85% of the requirement by the end of grade 12,
so a student could clear every benchmark and still not graduate.
"""
import pytest

from app.routes.graduation import (
    DEFAULT_CREDITS_PER_YEAR, TOTAL_REQUIRED, _risk_level,
    can_still_graduate_on_time, expected_credits_by_end_of, expected_progress,
    get_grad_policy,
)

R = TOTAL_REQUIRED          # 225
PER_YEAR = DEFAULT_CREDITS_PER_YEAR   # 80


# ── benchmarks ──

@pytest.mark.parametrize('grade,expected', [
    (9, 80), (10, 160), (11, 225), (12, 225),
])
def test_benchmarks_follow_capacity_capped_at_the_requirement(grade, expected):
    assert expected_credits_by_end_of(grade, R, PER_YEAR) == expected


def test_benchmark_never_exceeds_what_it_takes_to_graduate():
    """At 80/year, raw capacity by grade 11 is 240 — expecting that would
    demand more credits than the diploma requires."""
    for grade in (9, 10, 11, 12):
        assert expected_credits_by_end_of(grade, R, PER_YEAR) <= R


def test_senior_benchmark_equals_the_requirement():
    """The old curve topped out at 85% of the requirement, so a student could
    hit every benchmark and still be 34 credits short of graduating."""
    assert expected_credits_by_end_of(12, R, PER_YEAR) == R


def test_benchmarks_are_none_outside_high_school():
    for grade in (None, 0, 8, 13):
        assert expected_credits_by_end_of(grade, R, PER_YEAR) is None


# ── the regression that motivated this ──

@pytest.mark.parametrize('grade', [9, 10, 11, 12])
def test_student_failing_half_their_courses_is_never_on_track(grade):
    earned = (PER_YEAR / 2) * (grade - 8)
    level = _risk_level(earned, R, grade, per_year=PER_YEAR)
    assert level != 'on-track', f'grade {grade}: {earned} credits read as on-track'
    assert level == 'critical'


@pytest.mark.parametrize('grade', [9, 10, 11, 12])
def test_student_on_full_pace_is_on_track(grade):
    earned = PER_YEAR * (grade - 8)
    assert _risk_level(earned, R, grade, per_year=PER_YEAR) == 'on-track'


def test_risk_worsens_as_credits_fall():
    """Ordering sanity: the four levels appear in the right sequence."""
    seen = [_risk_level(c, R, 10, per_year=PER_YEAR)
            for c in (160, 150, 120, 40)]
    assert seen == ['on-track', 'warning', 'at-risk', 'critical']


# ── feasibility, which pace alone cannot express ──

def test_flags_a_student_who_mathematically_cannot_finish():
    """A junior with 100 credits and one 80-credit year left tops out at 180,
    short of 225. No pace ratio says that; the app could not detect it before."""
    assert can_still_graduate_on_time(100, 11, R, PER_YEAR) is False
    assert _risk_level(100, R, 11, per_year=PER_YEAR) == 'critical'


def test_feasible_student_is_not_force_flagged():
    assert can_still_graduate_on_time(160, 11, R, PER_YEAR) is True


def test_feasibility_can_only_worsen_the_verdict():
    """A student on full pace stays on-track — the check never downgrades
    someone who is genuinely fine."""
    assert can_still_graduate_on_time(240, 11, R, PER_YEAR) is True
    assert _risk_level(240, R, 11, per_year=PER_YEAR) == 'on-track'


# ── quarter interpolation ──

def test_quarters_interpolate_between_grade_benchmarks():
    """Grade 10 runs from 80 (end of 9th) to 160 (end of 10th)."""
    got = [expected_progress(10, quarter=q, total_required=R,
                             per_year=PER_YEAR)['credits_expected']
           for q in (1, 2, 3, 4)]
    assert got == [100, 120, 140, 160]


def test_expected_progress_is_none_outside_high_school():
    assert expected_progress(8) is None
    assert expected_progress(13) is None


def test_expected_progress_pct_is_relative_to_the_requirement():
    out = expected_progress(12, quarter=4, total_required=R, per_year=PER_YEAR)
    assert out['credits_pct'] == pytest.approx(1.0)


# ── the policy is configurable, not hardcoded ──

def test_policy_defaults_without_a_user():
    """Must work in scripts and tests with no request context."""
    policy = get_grad_policy(user=None)
    assert policy['required'] == R
    assert policy['per_year'] == PER_YEAR


def test_policy_reads_school_config(app):
    from app.models.user import User
    from app.utils.school_config import merge_school_config
    from app import db

    with app.app_context():
        u = User(username='policy_u', display_name='Policy', role='counselor')
        u.set_password('passw0rd123')
        db.session.add(u)
        db.session.commit()
        merge_school_config(u, {'credits_required': 260, 'credits_per_year': 60})

        policy = get_grad_policy(user=u)
        assert policy['required'] == 260
        assert policy['per_year'] == 60
        # A 6-period school: 60/yr, capped at 260 -> 60/120/180/240.
        assert expected_credits_by_end_of(10, 260, 60) == 120

        db.session.delete(u)
        db.session.commit()


@pytest.mark.parametrize('bad', ['', 'abc', None, 0, -5])
def test_bad_config_values_fall_back_to_defaults(app, bad):
    from app.models.user import User
    from app.utils.school_config import merge_school_config
    from app import db

    with app.app_context():
        u = User(username=f'policy_bad_{abs(hash(str(bad))) % 9999}',
                 display_name='Bad', role='counselor')
        u.set_password('passw0rd123')
        db.session.add(u)
        db.session.commit()
        merge_school_config(u, {'credits_required': bad, 'credits_per_year': bad})

        policy = get_grad_policy(user=u)
        assert policy['required'] == R
        assert policy['per_year'] == PER_YEAR

        db.session.delete(u)
        db.session.commit()


def test_settings_route_rejects_junk(app):
    from app.models.user import User
    from app import db
    with app.app_context():
        u = User(username='policy_route', display_name='Route', role='counselor',
                 setup_completed=True)
        u.set_password('passw0rd123')
        db.session.add(u)
        db.session.commit()
        uid = u.id

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(uid)
        sess['_fresh'] = True

    r = client.post('/settings/graduation-policy',
                    data={'credits_required': 'abc', 'credits_per_year': '80'})
    assert r.status_code == 302
    with app.app_context():
        assert get_grad_policy(user=db.session.get(User, uid))['required'] == R

    r = client.post('/settings/graduation-policy',
                    data={'credits_required': '240', 'credits_per_year': '80'})
    assert r.status_code == 302
    with app.app_context():
        u = db.session.get(User, uid)
        assert get_grad_policy(user=u)['required'] == 240
        db.session.delete(u)
        db.session.commit()
