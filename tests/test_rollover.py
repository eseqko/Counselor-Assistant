"""End-of-year rollover: WIP-aware default actions and anomaly flags."""
from app.utils.rollover import default_action, detect_anomalies, credit_status_summary


def test_senior_on_track_after_wip_defaults_graduate(app_ctx, make_student):
    # 200 completed + 25 WIP = 225 projected -> graduates despite raw 200/225.
    sid = make_student(grade=12, completed=200, wip=25, quarter='12-Q4', ag_met=7)
    from app.models.student import Student
    s = Student.query.get(sid)
    assert default_action(s) == 'graduate'
    assert not any('short of graduation' in f for f in detect_anomalies(s))


def test_senior_short_after_wip_defaults_skip(app_ctx, make_student):
    # 140 + 15 WIP = 155 projected, 70 short -> needs review (skip).
    sid = make_student(grade=12, completed=140, wip=15, quarter='12-Q4', ag_met=5)
    from app.models.student import Student
    s = Student.query.get(sid)
    assert default_action(s) == 'skip'
    flags = detect_anomalies(s)
    assert any('short of graduation' in f and '70 short' in f for f in flags)


def test_senior_within_slack_graduates(app_ctx, make_student):
    sid = make_student(grade=12, completed=220, wip=5, quarter='12-Q4', ag_met=7)
    from app.models.student import Student
    assert default_action(Student.query.get(sid)) == 'graduate'


def test_protected_status_senior_skips(app_ctx, make_student):
    # IEP senior is entitled to a 5th year -> never auto-graduate.
    sid = make_student(grade=12, completed=225, wip=0, quarter='12-Q4',
                       ag_met=7, iep_status=True)
    from app.models.student import Student
    s = Student.query.get(sid)
    assert default_action(s) == 'skip'
    assert any('5th year' in f for f in detect_anomalies(s))


def test_lower_grades_promote(app_ctx, make_student):
    for g in (9, 10, 11):
        sid = make_student(grade=g, completed=30, wip=0, quarter=f'{g}-Q3')
        from app.models.student import Student
        assert default_action(Student.query.get(sid)) == 'promote'


def test_behind_pace_lower_grade_flagged_but_still_promotes(app_ctx, make_student):
    sid = make_student(grade=10, completed=60, wip=0, quarter='10-Q3', ag_met=1)
    from app.models.student import Student
    s = Student.query.get(sid)
    assert default_action(s) == 'promote'
    assert any('behind pace' in f for f in detect_anomalies(s))


def test_zero_zero_returns_none_no_false_alarm(app_ctx, make_student):
    sid = make_student(grade=9, completed=0, wip=0, quarter='9-Q1', ag_met=0)
    from app.models.student import Student
    s = Student.query.get(sid)
    assert credit_status_summary(s) is None
    assert not any('credits' in f or 'short' in f for f in detect_anomalies(s))


def test_no_grade_level_skips(app_ctx, make_student):
    sid = make_student(grade=None)
    from app.models.student import Student
    assert default_action(Student.query.get(sid)) == 'skip'
