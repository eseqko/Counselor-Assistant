"""Student 360 action-plan engine tests.

Personas: a failing chronic-absent 9th grader (off_track, credit-recovery +
attendance items), a senior with FAFSA/deadline pressure (critical college
items), and a clean student (on_track, nothing critical). Plus targeted units:
the corrected chronic-absence math, retake detection, and GPA trend direction.
"""
from datetime import date, timedelta

import pytest

from app import db
from app.models.user import User
from app.models.student import Student
from app.models.grade import GradeRecord
from app.models.attendance import AttendanceRecord
from app.models.college_career import CollegeCareerPlan, CollegeApplication
from app.utils.next_steps import (
    build_action_plan, student_attendance_stats,
    failed_courses_needing_recovery, student_gpa_trend,
)

TODAY = date(2026, 3, 2)


@pytest.fixture
def env(app):
    with app.app_context():
        u = User(username='ns_c', display_name='NS', role='counselor',
                 setup_completed=True)
        u.set_password('passw0rd123')
        db.session.add(u)
        db.session.commit()
        yield u.id
        # Delete dependent rows FIRST: Student deletes don't cascade, and
        # SQLite recycles the freed ids — leftover grade/attendance rows would
        # silently attach to the next test's students.
        ns_ids = [r[0] for r in db.session.query(Student.id).filter(
            Student.student_id_number.like('NS-%')).all()]
        if ns_ids:
            GradeRecord.query.filter(GradeRecord.student_id.in_(ns_ids)).delete(
                synchronize_session=False)
            AttendanceRecord.query.filter(
                AttendanceRecord.student_id.in_(ns_ids)).delete(
                synchronize_session=False)
            plans = CollegeCareerPlan.query.filter(
                CollegeCareerPlan.student_id.in_(ns_ids)).all()
            for p in plans:
                CollegeApplication.query.filter_by(plan_id=p.id).delete(
                    synchronize_session=False)
                db.session.delete(p)
            Student.query.filter(Student.id.in_(ns_ids)).delete(
                synchronize_session=False)
        User.query.filter_by(username='ns_c').delete(synchronize_session=False)
        db.session.commit()


def _student(uid, sid, grade):
    s = Student(student_id_number=sid, first_name='T', last_name=sid,
                grade_level=grade, status='active', assigned_counselor_id=uid)
    db.session.add(s)
    db.session.flush()
    return s


def _grade(s, course, letter, year='2025-2026', quarter=2):
    db.session.add(GradeRecord(
        student_id=s.id, course_name=course, letter_grade=letter,
        grade_type='final', school_year=year, quarter=quarter))


def _attendance_days(s, n_days, absent_every=None, start=None):
    """n_days distinct days, 6 period rows each; every `absent_every`-th day has
    one absent period (rest present)."""
    start = start or (TODAY - timedelta(days=n_days + 5))
    for d in range(n_days):
        day = start + timedelta(days=d)
        is_absent_day = absent_every and (d % absent_every == 0)
        for p in range(1, 7):
            db.session.add(AttendanceRecord(
                student_id=s.id, date=day, period=p,
                status='absent' if (is_absent_day and p == 1) else 'present'))


def test_attendance_math_is_day_based(app, env):
    """3 absent days out of 20 enrolled days = 15% — even though only 3 of 120
    period ROWS are absent (the old math would have said 2.5%)."""
    with app.app_context():
        s = _student(env, 'NS-ATT', 10)
        _attendance_days(s, 20, absent_every=7)   # days 0,7,14 absent → 3 days
        db.session.commit()
        stats = student_attendance_stats(s, today=TODAY)
        assert stats['enrolled_days'] == 20
        assert stats['absent_days'] == 3
        assert stats['rate_pct'] == 15.0
        assert stats['level'] == 'chronic'


def test_recovery_excludes_retaken_courses(app, env):
    with app.app_context():
        s = _student(env, 'NS-REC', 11)
        _grade(s, 'Algebra I', 'F', quarter=1)
        _grade(s, 'Algebra I', 'C', quarter=3)     # retaken and passed
        _grade(s, 'Biology', 'NP', quarter=2)      # never retaken
        db.session.commit()
        needs = failed_courses_needing_recovery(s)
        assert [n['course'] for n in needs] == ['Biology']


def test_gpa_trend_declining(app, env):
    with app.app_context():
        s = _student(env, 'NS-GPA', 10)
        for c in ('English', 'Math', 'Science'):
            _grade(s, c, 'B', quarter=1)
        for c in ('English', 'Math', 'Science'):
            _grade(s, c, 'D', quarter=2)
        db.session.commit()
        trend = student_gpa_trend(s)
        assert trend['direction'] == 'declining'
        assert trend['series'][0]['gpa'] == 3.0
        assert trend['series'][1]['gpa'] == 1.0


def test_failing_freshman_is_off_track_with_recovery_items(app, env):
    with app.app_context():
        s = _student(env, 'NS-9F', 9)
        _grade(s, 'English 9', 'F', quarter=1)
        _grade(s, 'Algebra I', 'F', quarter=2)
        _attendance_days(s, 30, absent_every=5)    # 6/30 = 20% → chronic
        db.session.commit()

        from app.routes.graduation import _build_student_grad_data
        plan = build_action_plan(s, grad_data=_build_student_grad_data(s), today=TODAY)

        assert plan['on_track']['verdict'] == 'off_track'
        titles = [i['title'] for i in plan['items']]
        assert any('Retake English 9' in t for t in titles)
        assert any('Retake Algebra I' in t for t in titles)
        assert any('Chronic absence' in t for t in titles)
        # Chronic absence is a critical item
        assert any(i['priority'] == 'critical' and i['category'] == 'attendance'
                   for i in plan['items'])


def test_senior_fafsa_and_deadline_pressure(app, env):
    with app.app_context():
        s = _student(env, 'NS-12', 12)
        plan_row = CollegeCareerPlan(student_id=s.id, counselor_id=env,
                                     pathway='four_year', fafsa_status='not_started')
        db.session.add(plan_row)
        db.session.flush()
        db.session.add(CollegeApplication(
            plan_id=plan_row.id, college_name='CSU East Bay',
            status='in_progress', deadline=TODAY + timedelta(days=10)))
        db.session.commit()

        plan = build_action_plan(s, grad_data=None, today=TODAY)
        items = plan['items']
        fafsa = next(i for i in items if 'FAFSA' in i['title'])
        assert fafsa['priority'] == 'critical'
        deadline = next(i for i in items if 'CSU East Bay' in i['title'])
        assert deadline['priority'] == 'critical'      # <=14 days out
        assert 'due in 10 days' in deadline['title']
        # No SAT/ACT on file → flagged for a senior
        assert any('SAT/ACT' in i['title'] for i in items)


def test_clean_student_on_track_nothing_critical(app, env):
    with app.app_context():
        s = _student(env, 'NS-OK', 10)
        for c in ('English', 'Math', 'Science', 'History'):
            _grade(s, c, 'B', quarter=1)
            _grade(s, c, 'B+', quarter=2)
        _attendance_days(s, 40, absent_every=None)   # perfect attendance
        db.session.commit()

        plan = build_action_plan(s, grad_data=None, today=TODAY)
        assert plan['on_track']['verdict'] in ('on_track', 'at_risk')
        assert not any(i['priority'] == 'critical' for i in plan['items'])
        assert plan['attendance']['level'] == 'ok'
        assert any('Attendance healthy' in g for g in plan['on_track']['good'])
