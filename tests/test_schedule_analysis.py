"""Schedule completeness and prerequisite checking on a 4x4 block.

The case that motivated this: on a block schedule a prerequisite can be taken
in Q1-Q2 of the SAME year as the course it unlocks in Q3-Q4. Checking prior
years alone would wrongly flag half the master schedule.
"""
from types import SimpleNamespace

import pytest

from app.utils.prereq import CourseIndex, parse_prerequisite, rules_to_json
from app.utils.schedule_analysis import (
    DEFAULT_EXPECTED_CLASSES, analyze_completeness, analyze_student_schedule,
    build_completion_timeline, check_prerequisites, is_non_credit_title,
    term_key,
)

YEAR = '2026-2027'


def entry(number, title, period, term, year=YEAR, advisory=False, non_class=False):
    return SimpleNamespace(course_number=number, course_title=title,
                           period=period, term=term, school_year=year,
                           is_advisory=advisory, is_non_class=non_class)


def grade(number, letter, quarter, year=YEAR):
    return SimpleNamespace(course_number=number, letter_grade=letter,
                           quarter=quarter, school_year=year)


def course(number, prereq_text, index):
    rule = parse_prerequisite(prereq_text, index)
    return SimpleNamespace(course_number=number, prereq_rules_json=rules_to_json(rule))


MATH_INDEX = CourseIndex([
    ('22000', 'Math Course 1 CP'), ('22001', 'Math Course 1 CP'),
    ('22002', 'Math Course 2 CP'), ('22003', 'Math Course 2 CP'),
    ('22004', 'Math Course 3 CP'), ('22005', 'Math Course 3 CP'),
    ('26104A', 'Foods & Nutrition'), ('26108', 'Culinary Arts CP'),
])


def full_schedule():
    """4 academic periods x 2 half-year courses = 8 classes."""
    out = []
    for period in (1, 2, 3, 4):
        out.append(entry(f'{period}00', f'Course {period}A', period, 'Q1'))
        out.append(entry(f'{period}01', f'Course {period}A', period, 'Q2'))
        out.append(entry(f'{period}02', f'Course {period}B', period, 'Q3'))
        out.append(entry(f'{period}03', f'Course {period}B', period, 'Q4'))
    return out


# ── completeness ──

def test_a_full_schedule_is_eight_classes():
    out = analyze_completeness(full_schedule())
    assert out['classes'] == 8
    assert out['gaps'] == []
    assert out['is_complete'] is True


def test_a_hole_in_one_period_is_reported_with_the_quarter():
    entries = [e for e in full_schedule()
               if not (e.period == 3 and e.term == 'Q4')]
    out = analyze_completeness(entries)
    assert out['is_complete'] is False
    assert out['gaps'] == [{'period': 3, 'term': 'Q4'}]
    assert out['classes'] == 7.5


def test_year_long_course_covers_all_four_quarters():
    """A YR row fills its period for the whole year, not just one quarter."""
    entries = [entry('900', 'Yearlong Seminar', 1, 'YR')]
    out = analyze_completeness(entries)
    assert out['gaps'] == []
    assert out['classes'] == 2


def test_advisory_and_admin_rows_do_not_count_as_academic_periods():
    """Advisory sits in period 6 and the VP row in period 7; neither should
    create a period the student is then expected to fill all year."""
    entries = full_schedule() + [
        entry('0001', 'Advisory Period', 6, 'YR', advisory=True),
        entry('28436', 'Vice Principal', 7, 'YR', non_class=True),
    ]
    out = analyze_completeness(entries)
    assert out['periods'] == [1, 2, 3, 4]
    assert out['gaps'] == []
    assert out['classes'] == 8


@pytest.mark.parametrize('title', [
    'Early Release', 'Late Arrival', 'Mid-Year Grad', 'MID YEAR GRAD',
    'Off Campus Work Experience',
])
def test_non_credit_placements_are_recognized(title):
    assert is_non_credit_title(title) is True


def test_non_credit_placement_still_fills_a_period():
    """It earns no credit but the student is not missing a class."""
    entries = [e for e in full_schedule()
               if not (e.period == 4 and e.term in ('Q3', 'Q4'))]
    entries += [entry('9100', 'Early Release', 4, 'Q3'),
                entry('9101', 'Early Release', 4, 'Q4')]
    out = analyze_completeness(entries)
    assert out['gaps'] == []
    assert out['classes'] == 8
    assert len(out['non_credit_entries']) == 2


def test_regular_course_is_not_mistaken_for_a_release():
    assert is_non_credit_title('Culinary Arts CP') is False
    assert is_non_credit_title('Early Childhood Education') is False


# ── term ordering ──

def test_term_key_orders_quarters_within_a_year():
    assert term_key(YEAR, 'Q1') < term_key(YEAR, 'Q2') < term_key(YEAR, 'Q4')


def test_term_key_orders_years():
    assert term_key('2025-2026', 'Q4') < term_key('2026-2027', 'Q1')


def test_year_long_sorts_before_quarters():
    """A YR course can't depend on something taken later in the same year."""
    assert term_key(YEAR, 'YR') < term_key(YEAR, 'Q1')


# ── prerequisites, the 4x4 case ──

def test_prereq_passed_earlier_the_same_year_satisfies_a_q3_course():
    """THE case: Math Course 2 in Q1-Q2 unlocks Math Course 3 in Q3-Q4."""
    entries = [entry('22002', 'Math Course 2 CP', 1, 'Q1'),
               entry('22003', 'Math Course 2 CP', 1, 'Q2'),
               entry('22004', 'Math Course 3 CP', 1, 'Q3')]
    grades = [grade('22002', 'B', 1), grade('22003', 'B', 2)]
    courses = {'22004': course('22004', 'Pass MC2 with C- or better', MATH_INDEX)}

    findings = check_prerequisites(entries, build_completion_timeline(grades), courses)
    assert findings == [], f'same-year prerequisite wrongly flagged: {findings}'


def test_prereq_from_a_prior_year_satisfies():
    entries = [entry('22004', 'Math Course 3 CP', 1, 'Q1')]
    grades = [grade('22002', 'A', 3, year='2025-2026')]
    courses = {'22004': course('22004', 'Pass MC2 with C- or better', MATH_INDEX)}
    assert check_prerequisites(entries, build_completion_timeline(grades), courses) == []


def test_missing_prereq_is_flagged():
    entries = [entry('22004', 'Math Course 3 CP', 1, 'Q1')]
    courses = {'22004': course('22004', 'Pass MC2 with C- or better', MATH_INDEX)}
    findings = check_prerequisites(entries, {}, courses)
    assert len(findings) == 1
    assert findings[0]['status'] == 'missing'


def test_prereq_passed_with_too_low_a_grade_is_flagged_with_both_grades():
    entries = [entry('22004', 'Math Course 3 CP', 1, 'Q3')]
    grades = [grade('22002', 'D', 1)]
    courses = {'22004': course('22004', 'Pass MC2 with C- or better', MATH_INDEX)}
    findings = check_prerequisites(entries, build_completion_timeline(grades), courses)
    assert findings[0]['status'] == 'low_grade'
    assert 'earned D' in findings[0]['detail'] and 'needs C-' in findings[0]['detail']


def test_prereq_scheduled_earlier_but_ungraded_is_in_progress_not_a_violation():
    """Day one of the year: MC2 is in Q1, MC3 in Q3, nothing graded yet. The
    student hasn't failed anything — this is a re-check at the break."""
    entries = [entry('22002', 'Math Course 2 CP', 1, 'Q1'),
               entry('22004', 'Math Course 3 CP', 1, 'Q3')]
    courses = {'22004': course('22004', 'Pass MC2 with C- or better', MATH_INDEX)}
    findings = check_prerequisites(entries, {}, courses)
    assert [f['status'] for f in findings] == ['in_progress']


def test_prereq_taken_in_a_LATER_term_does_not_satisfy():
    """Ordering must be strict: MC2 in Q3 cannot unlock MC3 in Q1."""
    entries = [entry('22004', 'Math Course 3 CP', 1, 'Q1'),
               entry('22002', 'Math Course 2 CP', 1, 'Q3')]
    grades = [grade('22002', 'A', 3)]
    courses = {'22004': course('22004', 'Pass MC2 with C- or better', MATH_INDEX)}
    findings = check_prerequisites(entries, build_completion_timeline(grades), courses)
    assert findings[0]['status'] == 'missing'


def test_advisory_prereq_is_not_reported_as_a_violation():
    entries = [entry('26108', 'Culinary Arts CP', 3, 'Q3')]
    courses = {'26108': course('26108', 'Foods & Nutrition (recommended)', MATH_INDEX)}
    findings = check_prerequisites(entries, {}, courses)
    assert findings[0]['status'] == 'advisory'


def test_unparseable_prereq_asks_for_a_human_instead_of_guessing():
    entries = [entry('21100', 'ELD 1', 2, 'Q1')]
    courses = {'21100': course('21100', 'ELPAC Scores', MATH_INDEX)}
    findings = check_prerequisites(entries, {}, courses)
    assert findings[0]['status'] == 'review'
    assert 'ELPAC' in findings[0]['requirement']


def test_courses_without_prereqs_produce_nothing():
    entries = [entry('20011', 'American Government CP', 1, 'Q3')]
    courses = {'20011': course('20011', 'None', MATH_INDEX)}
    assert check_prerequisites(entries, {}, courses) == []


def test_advisory_and_admin_rows_are_never_prereq_checked():
    entries = [entry('0001', 'Advisory Period', 6, 'YR', advisory=True),
               entry('28436', 'Vice Principal', 7, 'YR', non_class=True)]
    courses = {'0001': course('0001', 'Pass MC2 with C- or better', MATH_INDEX)}
    assert check_prerequisites(entries, {}, courses) == []


# ── combined ──

def test_full_analysis_sorts_blocking_issues_first():
    entries = full_schedule() + [entry('22004', 'Math Course 3 CP', 5, 'Q1')]
    courses = {'22004': course('22004', 'Pass MC2 with C- or better', MATH_INDEX)}
    out = analyze_student_schedule(entries, [], courses)
    assert out['blocking_count'] == 1
    assert out['findings'][0]['status'] == 'missing'
    assert out['has_issues'] is True


def test_clean_schedule_reports_no_issues():
    out = analyze_student_schedule(full_schedule(), [], {})
    assert out['has_issues'] is False
    assert out['blocking_count'] == 0
    assert out['completeness']['classes'] == DEFAULT_EXPECTED_CLASSES
