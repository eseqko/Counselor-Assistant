"""D/F outcomes by section, for the counselor's own caseload only.

The traps this pins down: counting a student once per quarter instead of once,
treating an ungraded mark as a failure, and letting a three-student section top
a ranking on the strength of one D.
"""
from types import SimpleNamespace

import pytest

from app.utils.grade_outcomes import (
    MIN_SECTION_STUDENTS, build_section_outcomes, chart_payload, has_signal,
    is_failing, latest_grade_per_course, student_course_outcomes,
)

YEAR = '2026-2027'


def entry(student_id, number, teacher='Wong, J.', period=1, title='Math Course 3 CP',
          advisory=False, non_class=False):
    return SimpleNamespace(student_id=student_id, course_number=number,
                           teacher_name=teacher, period=period,
                           course_title=title, is_advisory=advisory,
                           is_non_class=non_class)


def grade(student_id, number, letter, quarter=1, gtype='final', year=YEAR):
    return SimpleNamespace(student_id=student_id, course_number=number,
                           letter_grade=letter, quarter=quarter,
                           grade_type=gtype, school_year=year)


def section(teacher, n, failing=0, start=1, number='22004'):
    """n students in one section, `failing` of them with a D."""
    entries, grades = [], []
    for i in range(start, start + n):
        entries.append(entry(i, number, teacher=teacher))
        grades.append(grade(i, number, 'D' if i - start < failing else 'B'))
    return entries, grades


# ── grade classification ──

@pytest.mark.parametrize('letter', ['D+', 'D', 'D-', 'F', 'NP', 'f', ' d '])
def test_failing_grades(letter):
    assert is_failing(letter) is True


@pytest.mark.parametrize('letter', ['A', 'B-', 'C', 'C-', 'P'])
def test_passing_grades_are_not_failing(letter):
    assert is_failing(letter) is False


@pytest.mark.parametrize('letter', ['NM', 'I', 'W', '', None])
def test_marks_with_no_signal_are_excluded_entirely(letter):
    """'NM' means the teacher hasn't graded yet. Counting it either way is
    wrong — it was excluded from both numerator AND denominator."""
    assert has_signal(letter) is False
    assert is_failing(letter) is False


def test_ungraded_course_does_not_dilute_or_inflate_a_rate():
    entries = [entry(1, '22004'), entry(2, '22004')]
    grades = [grade(1, '22004', 'F'), grade(2, '22004', 'NM')]
    out = build_section_outcomes(entries, grades)
    row = out['rows'][0]
    assert row['students'] == 1, 'ungraded student counted in the denominator'
    assert row['failing'] == 1
    assert row['rate'] == 1.0


# ── one grade per student-course ──

def test_latest_graded_term_wins():
    """A student who pulled a D up to a C must not be counted as both."""
    grades = [grade(1, '22004', 'D', quarter=1), grade(1, '22004', 'C', quarter=3)]
    assert latest_grade_per_course(grades) == {(1, '22004'): 'C'}


def test_final_grade_beats_a_progress_report_in_the_same_term():
    grades = [grade(1, '22004', 'F', quarter=2, gtype='progress'),
              grade(1, '22004', 'C', quarter=2, gtype='final')]
    assert latest_grade_per_course(grades) == {(1, '22004'): 'C'}


def test_a_student_is_counted_once_per_section_not_once_per_quarter():
    entries = [entry(1, '22004')]
    grades = [grade(1, '22004', 'D', quarter=q) for q in (1, 2, 3, 4)]
    out = build_section_outcomes(entries, grades)
    assert out['rows'][0]['students'] == 1
    assert out['rows'][0]['failing'] == 1


def test_a_prior_year_grade_does_not_override_this_year():
    grades = [grade(1, '22004', 'F', quarter=4, year='2025-2026'),
              grade(1, '22004', 'A', quarter=1, year=YEAR)]
    assert latest_grade_per_course(grades) == {(1, '22004'): 'A'}


# ── section grouping ──

def test_rate_is_failing_students_over_graded_students():
    entries, grades = section('Wong, J.', 10, failing=3)
    out = build_section_outcomes(entries, grades)
    row = out['rows'][0]
    assert row['students'] == 10 and row['failing'] == 3
    assert row['rate'] == pytest.approx(0.3)


def test_small_sections_are_never_ranked():
    """One D in a three-student section is 33% and means nothing."""
    small_e, small_g = section('Tiny, T.', MIN_SECTION_STUDENTS - 1, failing=2, start=100)
    big_e, big_g = section('Big, B.', 20, failing=2, start=200)
    out = build_section_outcomes(small_e + big_e, small_g + big_g)

    tiny = next(r for r in out['rows'] if r['label'] == 'Tiny, T.')
    assert tiny['small_sample'] is True
    assert tiny['rate'] >= 0.5, 'fixture should give the small section a bad rate'
    assert [r['label'] for r in out['rankable']] == ['Big, B.']
    assert out['rows'][-1]['label'] == 'Tiny, T.', 'small sample topped the list'
    assert out['suppressed'] == 1


def test_sections_rank_worst_first():
    a_e, a_g = section('Low, L.', 10, failing=1, start=1, number='C1')
    b_e, b_g = section('High, H.', 10, failing=6, start=20, number='C2')
    out = build_section_outcomes(a_e + b_e, a_g + b_g)
    assert [r['label'] for r in out['rankable']] == ['High, H.', 'Low, L.']


def test_advisory_and_admin_rows_are_excluded():
    entries = [entry(1, '0001', title='Advisory Period', advisory=True),
               entry(2, '28436', title='Vice Principal', non_class=True)]
    grades = [grade(1, '0001', 'F'), grade(2, '28436', 'F')]
    assert build_section_outcomes(entries, grades)['rows'] == []


def test_grades_without_a_matching_schedule_row_are_skipped():
    """Attribution comes from the schedule; a grade with no section can't be
    assigned to a teacher without guessing."""
    out = build_section_outcomes([], [grade(1, '22004', 'F')])
    assert out['rows'] == []


@pytest.mark.parametrize('dimension,expected', [
    ('teacher', 'Wong, J.'), ('period', 'Period 1'), ('course', 'Math Course 3 CP'),
])
def test_grouping_dimensions(dimension, expected):
    entries, grades = section('Wong, J.', 6, failing=1)
    out = build_section_outcomes(entries, grades, dimension=dimension)
    assert out['rows'][0]['label'] == expected


# ── cohort narrowing ──

def test_cohort_filter_narrows_the_population():
    entries, grades = section('Wong, J.', 10, failing=4)
    cohort_of = {i: ('Newcomer' if i <= 4 else 'EO') for i in range(1, 11)}
    out = build_section_outcomes(entries, grades, cohort_of=cohort_of,
                                 cohort_filter='Newcomer')
    row = out['rows'][0]
    assert row['students'] == 4, 'filter did not restrict the denominator'
    assert row['failing'] == 4
    assert row['rate'] == 1.0


def test_no_cohort_filter_counts_everyone():
    entries, grades = section('Wong, J.', 10, failing=4)
    cohort_of = {i: 'EO' for i in range(1, 11)}
    out = build_section_outcomes(entries, grades, cohort_of=cohort_of)
    assert out['rows'][0]['students'] == 10


# ── overall + chart ──

def test_overall_rate_spans_every_section():
    a_e, a_g = section('A', 10, failing=2, start=1, number='C1')
    b_e, b_g = section('B', 10, failing=4, start=20, number='C2')
    out = build_section_outcomes(a_e + b_e, a_g + b_g)
    assert out['overall_students'] == 20
    assert out['overall_failing'] == 6
    assert out['overall_rate'] == pytest.approx(0.3)


def test_empty_input_does_not_divide_by_zero():
    out = build_section_outcomes([], [])
    assert out['rows'] == [] and out['overall_rate'] == 0
    assert chart_payload(out) == {'labels': [], 'rates': [], 'students': []}


def test_chart_only_includes_rankable_sections():
    small_e, small_g = section('Tiny', MIN_SECTION_STUDENTS - 1, failing=2, start=100)
    big_e, big_g = section('Big', 8, failing=2, start=200)
    chart = chart_payload(build_section_outcomes(small_e + big_e, small_g + big_g))
    assert chart['labels'] == ['Big']


# ── per-student course outcomes (profile view) ──

def test_student_outcomes_flag_failing_courses():
    entries = [entry(1, 'C1', title='Math', period=1),
               entry(1, 'C2', title='English', period=2)]
    grades = [grade(1, 'C1', 'F'), grade(1, 'C2', 'B')]
    out = student_course_outcomes(entries, grades)
    assert out['failing_count'] == 1
    # Failing course is listed first.
    assert out['courses'][0]['course_title'] == 'Math'
    assert out['courses'][0]['failing'] is True
    assert out['courses'][1]['failing'] is False


def test_student_outcomes_collapse_semester_pairs():
    """A course split into [S1]/[S2] is one course to the counselor."""
    entries = [entry(1, '25248', title='Fashion Design CP [S1]', period=1),
               entry(1, '25248', title='Fashion Design CP [S1]', period=1)]
    grades = [grade(1, '25248', 'D')]
    out = student_course_outcomes(entries, grades)
    assert len(out['courses']) == 1


def test_student_outcomes_show_ungraded_without_counting_them():
    entries = [entry(1, 'C1', title='Chem', period=1)]
    grades = [grade(1, 'C1', 'NM')]
    out = student_course_outcomes(entries, grades)
    assert out['failing_count'] == 0
    assert out['courses'][0]['graded'] is False
    assert out['courses'][0]['failing'] is False


def test_student_outcomes_use_latest_graded_term():
    entries = [entry(1, 'C1', title='Math', period=1)]
    grades = [grade(1, 'C1', 'F', quarter=1), grade(1, 'C1', 'C', quarter=3)]
    out = student_course_outcomes(entries, grades)
    assert out['courses'][0]['letter'] == 'C'
    assert out['failing_count'] == 0


def test_student_outcomes_exclude_advisory_and_admin():
    entries = [entry(1, '0001', title='Advisory Period', advisory=True),
               entry(1, '28436', title='Vice Principal', non_class=True)]
    grades = [grade(1, '0001', 'F'), grade(1, '28436', 'F')]
    out = student_course_outcomes(entries, grades)
    assert out['courses'] == []
    assert out['failing_count'] == 0
