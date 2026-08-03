"""Cohort concentration: is a group clustered into particular sections?

The arithmetic here is the whole feature — a raw count of "8 Newcomers in
period 2" means nothing until you know whether that's 8 of 10 or 8 of 200. The
concentration index is the cohort's share of a section divided by its share of
the caseload, so 2.0 means twice the representation blind scheduling would give.

Uses lightweight stand-ins rather than ORM rows: build_concentration is a pure
function and the maths should be provable without a database.
"""
from types import SimpleNamespace

import pytest

from app.utils.cohort_concentration import (
    MIN_SLICE_FOR_FLAG, build_concentration, chart_payload, schedule_key,
)


def entry(student_id, period=1, term='Q1', teacher='Smith, A.',
          title='Algebra', section='1-001', advisory=False, non_class=False):
    return SimpleNamespace(
        student_id=student_id, period=period, term=term,
        teacher_name=teacher, course_title=title, section_id=section,
        is_advisory=advisory, is_non_class=non_class,
    )


def students(n):
    return [SimpleNamespace(id=i) for i in range(1, n + 1)]


# ── slice keys ──

def test_schedule_key_per_dimension():
    e = entry(1, period=3, teacher='Mar, J.', title='Jewelry CP', section='3-532')
    assert schedule_key(e, 'period') == 'Period 3'
    assert schedule_key(e, 'teacher') == 'Mar, J.'
    assert schedule_key(e, 'course') == 'Jewelry CP'
    assert schedule_key(e, 'advisory') == '3-532'
    assert schedule_key(e, 'nonsense') is None


def test_schedule_key_none_when_field_missing():
    assert schedule_key(entry(1, period=None), 'period') is None
    assert schedule_key(entry(1, teacher=''), 'teacher') is None


# ── the core arithmetic ──

def test_index_is_one_when_perfectly_proportional():
    """Half the caseload is Newcomer and half of the period is too."""
    cohort_of = {1: 'Newcomer', 2: 'Newcomer', 3: 'EO', 4: 'EO'}
    entries = [entry(i, period=1) for i in (1, 2, 3, 4)]
    out = build_concentration(students(4), entries, cohort_of, 'period')

    cell = next(c for c in out['rows'][0]['cells'] if c['cohort'] == 'Newcomer')
    assert cell['count'] == 2
    assert cell['share'] == pytest.approx(0.5)
    assert cell['index'] == pytest.approx(1.0)
    assert cell['flagged'] is False


def test_index_detects_over_representation():
    """1 in 10 of the caseload is Newcomer, but 5 of 6 in period 2 are."""
    cohort_of = {i: ('Newcomer' if i <= 5 else 'EO') for i in range(1, 51)}
    entries = ([entry(i, period=2) for i in range(1, 6)] + [entry(6, period=2)]
               + [entry(i, period=1) for i in range(7, 51)])
    out = build_concentration(students(50), entries, cohort_of, 'period')

    p2 = next(r for r in out['rows'] if r['label'] == 'Period 2')
    cell = next(c for c in p2['cells'] if c['cohort'] == 'Newcomer')
    assert cell['count'] == 5
    assert p2['total'] == 6
    assert cell['index'] == pytest.approx((5 / 6) / (5 / 50))
    assert cell['flagged'] is True
    assert out['flagged'][0]['slice'] == 'Period 2'


def test_a_student_is_counted_once_per_slice_not_once_per_term():
    """The trap: a student in period 2 all four quarters has four rows."""
    cohort_of = {1: 'Newcomer'}
    entries = [entry(1, period=2, term=t) for t in ('Q1', 'Q2', 'Q3', 'Q4')]
    out = build_concentration(students(1), entries, cohort_of, 'period')

    row = out['rows'][0]
    assert row['total'] == 1, 'same student counted more than once'
    assert row['cells'][0]['count'] == 1


def test_term_filter_narrows_to_one_quarter():
    cohort_of = {1: 'Newcomer', 2: 'EO'}
    entries = [entry(1, period=2, term='Q1'), entry(2, period=2, term='Q3')]

    q1 = build_concentration(students(2), entries, cohort_of, 'period', term='Q1')
    assert q1['rows'][0]['total'] == 1

    both = build_concentration(students(2), entries, cohort_of, 'period', term='all')
    assert both['rows'][0]['total'] == 2


def test_small_slices_are_never_flagged():
    """One extra student swings the index wildly below this size, and naming a
    teacher on the strength of two students invites a bad conversation."""
    n = MIN_SLICE_FOR_FLAG - 1
    cohort_of = {i: ('Newcomer' if i == 1 else 'EO') for i in range(1, 51)}
    entries = ([entry(1, period=2)]
               + [entry(i, period=2) for i in range(2, n + 1)]
               + [entry(i, period=1) for i in range(n + 1, 51)])
    out = build_concentration(students(50), entries, cohort_of, 'period')

    p2 = next(r for r in out['rows'] if r['label'] == 'Period 2')
    assert p2['total'] < MIN_SLICE_FOR_FLAG
    assert all(c['flagged'] is False for c in p2['cells'])
    assert all(c['small_sample'] for c in p2['cells'])
    assert out['flagged'] == []


def test_non_class_rows_are_excluded():
    """A period-7 'Vice Principal' assignment is not a section anyone sits in."""
    cohort_of = {1: 'Newcomer'}
    entries = [entry(1, period=7, title='Vice Principal', non_class=True)]
    out = build_concentration(students(1), entries, cohort_of, 'period')
    assert out['rows'] == []


def test_advisory_dimension_only_counts_advisory_rows():
    cohort_of = {1: 'Newcomer', 2: 'EO'}
    entries = [
        entry(1, period=6, section='6-011 12th', advisory=True),
        entry(1, period=1, section='1-019'),        # regular class, ignored
        entry(2, period=6, section='6-011 12th', advisory=True),
    ]
    out = build_concentration(students(2), entries, cohort_of, 'advisory')
    assert [r['label'] for r in out['rows']] == ['6-011 12th']
    assert out['rows'][0]['total'] == 2


def test_students_outside_the_caseload_are_ignored():
    """Entries can only ever contribute to the counselor's own caseload."""
    cohort_of = {1: 'Newcomer'}
    entries = [entry(1, period=1), entry(999, period=1)]
    out = build_concentration(students(1), entries, cohort_of, 'period')
    assert out['rows'][0]['total'] == 1


def test_periods_sort_numerically():
    """'Period 10' must not sort between 'Period 1' and 'Period 2'."""
    cohort_of = {i: 'EO' for i in range(1, 4)}
    entries = [entry(1, period=10), entry(2, period=2), entry(3, period=1)]
    out = build_concentration(students(3), entries, cohort_of, 'period')
    assert [r['label'] for r in out['rows']] == ['Period 1', 'Period 2', 'Period 10']


def test_empty_caseload_does_not_divide_by_zero():
    out = build_concentration([], [], {}, 'period')
    assert out['rows'] == []
    assert out['total_students'] == 0
    assert out['flagged'] == []


def test_cohort_with_zero_members_yields_zero_index_not_error():
    cohort_of = {1: 'EO', 2: 'EO'}
    entries = [entry(1, period=1), entry(2, period=1)]
    out = build_concentration(students(2), entries, cohort_of, 'period')
    assert all(c['index'] >= 0 for r in out['rows'] for c in r['cells'])


# ── chart payload ──

def test_chart_payload_aligns_series_with_labels():
    cohort_of = {1: 'Newcomer', 2: 'EO', 3: 'EO'}
    entries = [entry(1, period=1), entry(2, period=1), entry(3, period=2)]
    out = build_concentration(students(3), entries, cohort_of, 'period')
    chart = chart_payload(out)

    assert chart['labels'] == ['Period 1', 'Period 2']
    for series in chart['series']:
        assert len(series['data']) == len(chart['labels'])
    eo = next(s for s in chart['series'] if s['name'] == 'EO')
    assert eo['data'] == [1, 1]
    newcomer = next(s for s in chart['series'] if s['name'] == 'Newcomer')
    assert newcomer['data'] == [1, 0]
