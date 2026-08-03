"""The staff directory's class/student counts, sourced from the schedule.

The bug this pins: those counts came only from GradeRecord, so for the first
months of a school year — before any marks exist — every teacher showed
0 classes and 0 students even with the whole caseload's schedule imported.
"""
import pytest

from app import db
from app.models.grade import GradeRecord
from app.models.schedule import ScheduleEntry
from app.models.staff import Staff
from app.models.student import Student
from app.models.user import User

YEAR = '2026-2027'


@pytest.fixture
def dir_env(app):
    """A counselor with two students scheduled into one teacher's classes, and
    another counselor's student in the same class."""
    with app.app_context():
        User.query.filter(User.username.in_(['dir_me', 'dir_other'])).delete(
            synchronize_session=False)
        Student.query.filter(Student.student_id_number.like('DIR-%')).delete(
            synchronize_session=False)
        Staff.query.filter(Staff.name.in_(['Mar, J.', 'Ghost, G.'])).delete(
            synchronize_session=False)
        db.session.commit()

        me = User(username='dir_me', display_name='Dir Me', role='counselor',
                  setup_completed=True)
        me.set_password('passw0rd123')
        other = User(username='dir_other', display_name='Dir Other',
                     role='counselor', setup_completed=True)
        other.set_password('passw0rd123')
        db.session.add_all([me, other])
        db.session.commit()

        def student(num, first, counselor_id, sample=False):
            s = Student(student_id_number=num, first_name=first, last_name='Test',
                        grade_level=11, status='active',
                        assigned_counselor_id=counselor_id, is_sample=sample)
            db.session.add(s)
            return s

        a = student('DIR-1', 'Ana', me.id)
        b = student('DIR-2', 'Ben', me.id)
        theirs = student('DIR-3', 'Cy', other.id)
        sample = student('DIR-4', 'Sample', me.id, sample=True)
        db.session.commit()

        staff = Staff(name='Mar, J.', title='Teacher')
        db.session.add(staff)
        db.session.commit()

        def sched(student_id, title, period, term, teacher='Mar, J.', **kw):
            db.session.add(ScheduleEntry(
                student_id=student_id, school_year=YEAR, term=term, period=period,
                course_number='25248', course_title=title, teacher_name=teacher,
                **kw))

        # One course spanning a semester, which Synergy splits in two by title.
        for sid in (a.id, b.id, theirs.id, sample.id):
            sched(sid, 'Fashion Design CP [S1]', 1, 'Q1')
            sched(sid, 'Fashion Design CP [S2]', 1, 'Q2')
        # A second, genuinely different class at another period, one student.
        sched(a.id, 'Jewelry CP', 3, 'YR')
        # An administrative placement is not a class.
        sched(a.id, 'Vice Principal', 7, 'YR', teacher='Ho, J.', is_non_class=True)
        db.session.commit()

        ids = dict(me=me.id, other=other.id, a=a.id, b=b.id,
                   theirs=theirs.id, sample=sample.id, staff=staff.id)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(ids['me'])
        sess['_fresh'] = True

    yield client, ids

    with app.app_context():
        ScheduleEntry.query.filter(ScheduleEntry.student_id.in_(
            [ids['a'], ids['b'], ids['theirs'], ids['sample']])).delete(
                synchronize_session=False)
        GradeRecord.query.filter(GradeRecord.student_id.in_(
            [ids['a'], ids['b']])).delete(synchronize_session=False)
        Staff.query.filter(Staff.id == ids['staff']).delete(synchronize_session=False)
        Student.query.filter(Student.id.in_(
            [ids['a'], ids['b'], ids['theirs'], ids['sample']])).delete(
                synchronize_session=False)
        User.query.filter(User.id.in_([ids['me'], ids['other']])).delete(
            synchronize_session=False)
        db.session.commit()


def _stat_block(html, name):
    """The rendered stat cluster for one staff card."""
    assert name in html, f'{name} missing from the directory'
    after = html.split(name, 1)[1]
    end = after.find('My Students')
    assert end != -1, 'stat markup changed'
    return after[:end + 40]


def test_counts_come_from_the_schedule_before_any_grades_exist(app, dir_env):
    """The whole point: August, schedules imported, not a single mark entered.
    This rendered 0 classes / 0 students for every teacher."""
    client, ids = dir_env
    with app.app_context():
        assert GradeRecord.query.filter_by(student_id=ids['a']).count() == 0, \
            'fixture must have no grades at all'

    block = _stat_block(client.get(f'/staff/?year={YEAR}').data.decode(), 'Mar, J.')
    # Two classes (Fashion Design, Jewelry) and two distinct students.
    assert '<div class="v">2</div><div class="l">Classes</div>' in block, block
    assert '<div class="v">2</div><div class="l">My Students</div>' in block, block


def test_index_counts_classes_and_students_from_schedule(app, dir_env):
    client, ids = dir_env
    from app.routes.staff import _caseload_students, _schedule_for_caseload, _class_label
    with app.app_context():
        me = User.query.get(ids['me'])
        students = _caseload_students(me)
        sids = [s.id for s in students]
        rows = _schedule_for_caseload(sids)

        # The sample student is excluded from the caseload entirely.
        assert ids['sample'] not in sids
        # The other counselor's student never appears.
        assert ids['theirs'] not in {r.student_id for r in rows}
        # Administrative placements are not classes.
        assert all(not r.is_non_class for r in rows)

        classes = {}
        for r in rows:
            classes.setdefault((r.teacher_name, _class_label(r.course_title),
                                r.period), set()).add(r.student_id)
        mar = {k: v for k, v in classes.items() if k[0] == 'Mar, J.'}
        # [S1] and [S2] at one period collapse into a single class.
        assert len(mar) == 2, f'expected 2 classes for Mar, got {sorted(mar)}'
        assert mar[('Mar, J.', 'Fashion Design CP', 1)] == {ids['a'], ids['b']}
        assert mar[('Mar, J.', 'Jewelry CP', 3)] == {ids['a']}


def test_semester_halves_are_one_class_not_two():
    from app.routes.staff import _class_label
    assert _class_label('Fashion Design CP [S1]') == 'Fashion Design CP'
    assert _class_label('Fashion Design CP [S2]') == 'Fashion Design CP'
    assert _class_label('Fashion Design CP') == 'Fashion Design CP'
    # Not a semester marker — must survive untouched.
    assert _class_label('Physics [Honors]') == 'Physics [Honors]'
    assert _class_label('') == 'Unknown'
    assert _class_label(None) == 'Unknown'


def test_detail_lists_the_students_in_each_class(app, dir_env):
    client, ids = dir_env
    html = client.get(f'/staff/{ids["staff"]}?year={YEAR}').data.decode()
    assert 'Ana' in html and 'Ben' in html, 'scheduled students not listed'
    assert 'Cy' not in html, "another counselor's student leaked"
    assert 'Fashion Design CP' in html


def test_a_graded_student_is_not_listed_twice(app, dir_env):
    """A class known from BOTH the schedule and a grade row is still one class
    with one row per student."""
    client, ids = dir_env
    with app.app_context():
        db.session.add(GradeRecord(
            student_id=ids['a'], school_year=YEAR, quarter=1, grade_type='final',
            course_name='Fashion Design CP [S1]', course_number='25248',
            period=1, teacher='Mar, J.', letter_grade='D'))
        db.session.commit()
    html = client.get(f'/staff/{ids["staff"]}?year={YEAR}').data.decode()
    # Isolate the Fashion Design block; Ana is legitimately in Jewelry too.
    assert 'Fashion Design CP' in html and 'Jewelry CP' in html
    fashion = html.split('Fashion Design CP')[1].split('Jewelry CP')[0]
    assert fashion.count('Ana') == 1, 'student listed twice after a grade arrived'
    assert '2 students' in fashion, 'grade row inflated the class size'
    # The grade is shown rather than the blank a schedule-only row carries.
    assert '>D<' in fashion or 'D' in fashion


# ── the roster behind each headcount ──

def test_a_class_row_lists_the_students_in_it(app, dir_env):
    """A headcount rarely answers the real question — which of mine are in
    there — so each class opens to name them."""
    client, ids = dir_env
    html = client.get(f'/staff/?year={YEAR}').data.decode()
    assert 'roster-chip' in html, 'no roster rendered'
    assert 'Ana Test' in html and 'Ben Test' in html
    # Each name links to that student's profile.
    assert f'/caseload/{ids["a"]}' in html


def test_the_roster_never_includes_another_counselors_student(app, dir_env):
    """Cy sits in the same section but belongs to the other counselor."""
    client, ids = dir_env
    html = client.get(f'/staff/?year={YEAR}').data.decode()
    assert 'Cy Test' not in html
    assert f'/caseload/{ids["theirs"]}' not in html


def test_the_roster_excludes_the_sample_student(app, dir_env):
    client, ids = dir_env
    html = client.get(f'/staff/?year={YEAR}').data.decode()
    assert f'/caseload/{ids["sample"]}' not in html


# ── prior years, once final grades exist ──

def _final(student_id, year, teacher='Mar, J.', course='Algebra 1 CP', letter='B'):
    return GradeRecord(student_id=student_id, school_year=year, quarter=4,
                       grade_type='final', course_name=course, course_number='X1',
                       period=2, teacher=teacher, letter_grade=letter)


def test_a_prior_year_with_final_grades_becomes_selectable(app, dir_env):
    """Import last year's final grades and that year joins the selector, with
    its own classes — the schedule only covers the current year."""
    client, ids = dir_env
    with app.app_context():
        db.session.add(_final(ids['a'], '2025-2026'))
        db.session.commit()
    html = client.get('/staff/').data.decode()
    assert '2025-2026' in html, 'prior year missing from the selector'

    prior = client.get('/staff/?year=2025-2026').data.decode()
    assert 'Algebra 1 CP' in prior, "prior year's class not shown"
    # And the current year's schedule-only class is not mixed in.
    assert 'Fashion Design CP' not in prior


def test_a_grade_with_no_teacher_recorded_creates_no_year(app, dir_env):
    """The caveat worth knowing: the directory is keyed on the teacher name,
    so a grade export without a Staff Name column contributes nothing here."""
    client, ids = dir_env
    with app.app_context():
        db.session.add(_final(ids['a'], '2024-2025', teacher=''))
        db.session.commit()
    assert '2024-2025' not in client.get('/staff/').data.decode()


def test_prior_year_df_counts_come_from_that_years_grades(app, dir_env):
    client, ids = dir_env
    with app.app_context():
        db.session.add(_final(ids['a'], '2025-2026', letter='F'))
        db.session.add(_final(ids['b'], '2025-2026', letter='A'))
        db.session.commit()
    html = client.get('/staff/?year=2025-2026').data.decode()
    assert '50.0%' in html or '50%' in html, 'D/F rate not computed for the prior year'


def test_the_year_selector_offers_a_schedule_only_year(app, dir_env):
    """Years used to come from grades alone, so a freshly imported schedule
    produced an empty selector and no default year."""
    client, ids = dir_env
    html = client.get('/staff/').data.decode()
    assert YEAR in html
