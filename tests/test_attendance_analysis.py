"""The attendance-analysis port, pinned against the source tool's own tests.

The counselor also uses the standalone Attendance Tracker these formulas came
from (tests/test_metrics_patterns.py and test_metrics_rates_tiers.py there).
The two tools must agree number-for-number, so the fixtures and expected
values here mirror that suite — same dates, same students, same answers.
"""
from datetime import date
from types import SimpleNamespace

import pytest

from app.utils.attendance_analysis import (
    ABSENT_DAY_THRESHOLD, build_day_status, build_student_metrics, by_month,
    by_period, by_weekday, compute_streaks, compute_trend, densify_day_status,
    infer_periods_per_day, is_exception_report, mon_fri_flag, period_skips,
    period_table, per_student_counts, school_calendar, summarize_population,
    tier_for, week_start, weekday_rates, weekly_rates,
)


def row(sid, day, status, period=None):
    return SimpleNamespace(student_id=sid, date=day, status=status, period=period)


def daily_rows(sid, calendar, absent_dates, status='absent'):
    """One daily row per calendar day: absent on the given dates, else present."""
    return [row(sid, d, status if d in absent_dates else 'present')
            for d in calendar]


def d(iso):
    return date.fromisoformat(iso)


# ── tiers: the 5/10/20 ladder with exact boundaries ──

@pytest.mark.parametrize('absent,enrolled,tier', [
    (0, 180, 'satisfactory'),
    (8, 180, 'satisfactory'),      # 4.44%
    (9, 180, 'at_risk'),           # exactly 5% — boundary belongs to the tier
    (17, 180, 'at_risk'),          # 9.44%
    (18, 180, 'chronic'),          # exactly 10%
    (35, 180, 'chronic'),          # 19.4%
    (36, 180, 'severe'),           # exactly 20%
    (180, 180, 'severe'),
    (1, 20, 'at_risk'),            # exactly 5% on a small denominator
    (2, 20, 'chronic'),            # exactly 10%
])
def test_tier_boundaries_are_exact(absent, enrolled, tier):
    """Cross-multiplication, not division: 9/180 must be at_risk, not a float
    hair under 5% that rounds back to satisfactory."""
    assert tier_for(absent, enrolled) == tier


def test_no_enrolled_days_means_no_tier():
    assert tier_for(0, 0) is None


# ── day status: the >=50% rule and dominant status ──

def test_a_daily_absent_row_is_an_absent_day():
    days = build_day_status([row('A', d('2025-09-08'), 'absent')])
    day = days[('A', d('2025-09-08'))]
    assert day['is_absent_day'] and day['dominant_status'] == 'absent_unexcused'


def test_half_of_periods_missed_is_an_absent_day():
    rows = [row('A', d('2025-09-08'), 'absent', period=p) for p in (1, 2, 3)]
    rows += [row('A', d('2025-09-08'), 'present', period=p) for p in (4, 5, 6)]
    day = build_day_status(rows)[('A', d('2025-09-08'))]
    assert day['periods_scheduled'] == 6 and day['periods_absent'] == 3
    assert day['is_absent_day'], '3 of 6 is exactly the 50% threshold'


def test_below_threshold_is_partial_not_absent():
    rows = [row('A', d('2025-09-08'), 'absent', period=1)]
    rows += [row('A', d('2025-09-08'), 'present', period=p) for p in (2, 3, 4)]
    day = build_day_status(rows)[('A', d('2025-09-08'))]
    assert not day['is_absent_day'] and day['is_partial']
    assert day['dominant_status'] == 'partial'


def test_dominant_status_ties_go_to_unexcused():
    rows = [row('A', d('2025-09-08'), 'absent', period=1),
            row('A', d('2025-09-08'), 'excused', period=2)]
    day = build_day_status(rows)[('A', d('2025-09-08'))]
    assert day['dominant_status'] == 'absent_unexcused'


def test_excused_majority_day_is_dominant_excused():
    rows = [row('A', d('2025-09-08'), 'excused', period=1),
            row('A', d('2025-09-08'), 'excused', period=2),
            row('A', d('2025-09-08'), 'absent', period=3)]
    day = build_day_status(rows)[('A', d('2025-09-08'))]
    assert day['is_absent_day'] and day['dominant_status'] == 'absent_excused'


def test_a_tardy_day_is_not_an_absent_day():
    day = build_day_status([row('A', d('2025-09-08'), 'tardy')])[
        ('A', d('2025-09-08'))]
    assert not day['is_absent_day'] and day['is_tardy_day']
    assert day['dominant_status'] == 'tardy'


# ── counts: excused/unexcused split absent DAYS by dominant status ──

def test_per_student_counts_split_absent_days_by_dominant_status():
    cal = [d('2025-09-08'), d('2025-09-09'), d('2025-09-10')]
    rows = (daily_rows('A', cal, {d('2025-09-08')})               # unexcused day
            + [row('A', d('2025-09-09'), 'excused')]              # excused day
            + [row('A', d('2025-09-10'), 'present')])
    rows = [r for r in rows if not (r.date == d('2025-09-09') and r.status == 'present')]
    counts = per_student_counts(build_day_status(rows))['A']
    assert counts['days_enrolled'] == 3
    assert counts['days_absent'] == 2
    assert counts['days_unexcused'] == 1 and counts['days_excused'] == 1


# ── streaks: the tracker's exact weekend-spanning fixture ──

def test_compute_streaks_span_weekends():
    """Thu, Fri, [weekend], Mon, Tue, Wed — Fri+Mon is ONE streak of 2."""
    cal = [d('2025-09-11'), d('2025-09-12'), d('2025-09-15'),
           d('2025-09-16'), d('2025-09-17')]
    rows = (daily_rows('A', cal, {d('2025-09-12'), d('2025-09-15')})
            + daily_rows('B', cal, {d('2025-09-11'), d('2025-09-16'),
                                    d('2025-09-17')})
            + daily_rows('C', cal, set()))
    calendar = school_calendar(rows)
    assert len(calendar) == 5
    streaks = compute_streaks(build_day_status(rows), calendar)
    assert streaks['A'] == {'current': 0, 'max': 2}   # attended the last day
    assert streaks['B'] == {'current': 2, 'max': 2}   # run ends on the last day
    assert streaks['C'] == {'current': 0, 'max': 0}


# ── Monday/Friday pattern: the tracker's exact three-student fixture ──

def _bdate_range(start, end):
    out, cur = [], d(start)
    while cur <= d(end):
        if cur.weekday() < 5:
            out.append(cur)
        cur = cur.replace(day=cur.day)  # no-op; advance below
        from datetime import timedelta
        cur = cur + timedelta(days=1)
    return out


def test_mon_fri_flags_tracker_fixture():
    cal = _bdate_range('2025-09-01', '2025-09-26')
    assert len(cal) == 20                       # 4 full Mon-Fri weeks
    fridays = {d('2025-09-05'), d('2025-09-12'), d('2025-09-19'), d('2025-09-26')}

    fri_rows = daily_rows('FRI', cal, fridays | {d('2025-09-01')})   # 5 absences
    uni_rows = daily_rows('UNI', cal, {d('2025-09-08'), d('2025-09-09'),
                                       d('2025-09-10'), d('2025-09-11'),
                                       d('2025-09-12')})             # 1 full week
    two_rows = daily_rows('TWO', cal, {d('2025-09-05'), d('2025-09-19')})

    rates = weekday_rates(build_day_status(fri_rows + uni_rows + two_rows))

    fri = rates['FRI']
    assert fri[4] == {'enrolled': 4, 'absent': 4}      # every Friday
    assert fri[0]['absent'] / fri[0]['enrolled'] == 0.25
    assert fri[2]['absent'] == 0

    assert mon_fri_flag(rates['FRI']) is True          # Friday skipper
    assert mon_fri_flag(rates['UNI']) is False         # uniform absentee
    assert mon_fri_flag(rates['TWO']) is False         # under the 5-absence minimum


# ── weekly rates: week starts Monday; partial weeks count their real days ──

def test_weekly_rates_hand_checked():
    cal = [d('2025-09-08'), d('2025-09-09'), d('2025-09-10'), d('2025-09-11'),
           d('2025-09-12'), d('2025-09-15'), d('2025-09-16'), d('2025-09-17'),
           d('2025-09-18')]
    weekly = weekly_rates(build_day_status(
        daily_rows('W1', cal, {d('2025-09-09')})))['W1']
    assert len(weekly) == 2
    week, school, absent, rate = weekly[0]
    assert week == d('2025-09-08') and school == 5 and absent == 1
    assert abs(rate - 0.8) < 1e-9
    week2, school2, _, rate2 = weekly[1]
    assert week2 == d('2025-09-15') and school2 == 4 and abs(rate2 - 1.0) < 1e-9


def test_week_start_is_monday():
    assert week_start(d('2025-09-11')) == d('2025-09-08')   # Thursday -> Monday
    assert week_start(d('2025-09-08')) == d('2025-09-08')


# ── trend classification: the tracker's exact slopes ──

def _weekly(rates):
    from datetime import timedelta
    start = d('2025-09-08')
    return [(start + timedelta(weeks=i), 5, 0, r) for i, r in enumerate(rates)]


def test_compute_trend_classification():
    label, slope = compute_trend(_weekly([1.0, 0.97, 0.94, 0.91, 0.88, 0.85]))
    assert label == 'declining' and abs(slope + 3.0) < 1e-8

    label, slope = compute_trend(_weekly([0.85, 0.88, 0.91, 0.94, 0.97, 1.0]))
    assert label == 'improving' and abs(slope - 3.0) < 1e-8

    label, slope = compute_trend(_weekly([0.9] * 6))
    assert label == 'stable' and abs(slope) < 1e-8

    label, slope = compute_trend(_weekly([1.0, 0.97, 0.94]))   # 3 weeks < min 4
    assert label == 'insufficient' and slope is None


def test_trend_uses_only_the_recent_window():
    """A bad start followed by six flat weeks is stable, not improving."""
    label, _ = compute_trend(_weekly([0.5, 0.5, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9]))
    assert label == 'stable'


# ── period skipping: the tracker's exact fixture ──

def test_period_table_and_skips():
    cal = _bdate_range('2025-09-08', '2025-09-19')
    assert len(cal) == 10
    rows = []
    for i, day in enumerate(cal):
        for period in range(1, 8):
            skip = 'absent' if (period == 5 and i < 4) else 'present'
            rows.append(row('PS', day, skip, period=period))
            uni = 'absent' if i < 4 else 'present'
            rows.append(row('UNI', day, uni, period=period))
    table = period_table(rows)
    ps5 = table['PS'][5]
    assert ps5['scheduled'] == 10 and ps5['unexcused'] == 4
    assert abs(ps5['rate'] - 0.4) < 1e-9
    assert table['PS'][1]['unexcused'] == 0
    assert table['UNI'][3]['unexcused'] == 4

    skips = period_skips(table)
    assert skips['PS'] == '5'
    assert skips['UNI'] is None            # uniform absence is not skipping


def test_tied_period_rates_break_to_the_lowest_period():
    """Two periods, identical qualifying rates: the tracker's stable sort
    keeps the first-listed (lowest) period. A differential run against the
    original caught this port picking the highest instead."""
    cal = _bdate_range('2025-09-08', '2025-09-19')
    rows = []
    for i, day in enumerate(cal):
        for period in (2, 6):
            status = 'absent' if i < 4 else 'present'
            rows.append(row('A', day, status, period=period))
        rows.append(row('A', day, 'present', period=1))
    assert period_skips(period_table(rows))['A'] == '2'


def test_two_misses_never_flag_a_period():
    rows = []
    cal = _bdate_range('2025-09-08', '2025-09-19')
    for i, day in enumerate(cal):
        for period in (1, 2):
            status = 'absent' if (period == 2 and i < 2) else 'present'
            rows.append(row('A', day, status, period=period))
    assert period_skips(period_table(rows))['A'] is None


# ── exception reports: densify fixes both denominators ──

def test_exception_report_is_detected_by_present_share():
    marks = [row('A', d('2025-09-08'), 'absent', period=p) for p in (1, 2)]
    assert is_exception_report(marks) is True
    full = marks + [row('A', d('2025-09-09'), 'present', period=p)
                    for p in range(1, 40)]
    assert is_exception_report(full) is False


def test_densify_turns_one_cut_into_a_partial_not_an_absent_day():
    """One marked period on a 6-period day must not read as a full absence."""
    marks = [row('A', d('2025-09-08'), 'absent', period=3),
             # Another student's fully-marked day reveals the schedule size.
             *[row('B', d('2025-09-08'), 'absent', period=p) for p in range(1, 7)]]
    days = build_day_status(marks)
    assert days[('A', d('2025-09-08'))]['is_absent_day'], 'pre-densify: wrong'
    fixed = densify_day_status(days, infer_periods_per_day(marks),
                               school_calendar(marks), {'A', 'B'})
    assert not fixed[('A', d('2025-09-08'))]['is_absent_day']
    assert fixed[('A', d('2025-09-08'))]['is_partial']
    assert fixed[('B', d('2025-09-08'))]['is_absent_day']


def test_densify_fills_unmarked_days_as_present():
    marks = [row('A', d('2025-09-08'), 'absent')]
    calendar = [d('2025-09-08'), d('2025-09-09'), d('2025-09-10')]
    fixed = densify_day_status(build_day_status(marks), 1, calendar, {'A'})
    counts = per_student_counts(fixed)['A']
    assert counts['days_enrolled'] == 3
    assert counts['days_absent'] == 1


# ── breakdowns ──

def test_by_weekday_covers_mon_to_fri_and_skips_weekends():
    cal = _bdate_range('2025-09-08', '2025-09-12')
    out = by_weekday(build_day_status(daily_rows('A', cal, {d('2025-09-08')})))
    assert [r['weekday'] for r in out] == list(
        ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'))
    assert out[0]['absent_days'] == 1 and out[0]['absence_rate'] == 1.0
    assert out[1]['absent_days'] == 0


def test_by_month_orders_and_rates():
    rows = (daily_rows('A', [d('2025-09-29'), d('2025-09-30')], {d('2025-09-30')})
            + daily_rows('A', [d('2025-10-01'), d('2025-10-02')], set()))
    out = by_month(build_day_status(rows))
    assert [r['month'] for r in out] == [d('2025-09-01'), d('2025-10-01')]
    assert out[0]['absence_rate'] == 0.5 and out[1]['absence_rate'] == 0.0


def test_by_period_counts_and_distinct_students():
    rows = [row('A', d('2025-09-08'), 'absent', period=1),
            row('B', d('2025-09-08'), 'absent', period=1),
            row('A', d('2025-09-09'), 'tardy', period=1),
            row('A', d('2025-09-08'), 'excused', period=2),
            row('A', d('2025-09-08'), 'present', period=3)]
    out = by_period(rows)
    p1 = next(r for r in out if r['period'] == 1)
    assert p1['unexcused'] == 2 and p1['tardies'] == 1 and p1['students'] == 2
    p2 = next(r for r in out if r['period'] == 2)
    assert p2['excused'] == 1
    assert all(r['period'] != 3 for r in out), 'present rows create no period row'


# ── assembly ──

def test_build_student_metrics_end_to_end():
    cal = _bdate_range('2025-09-01', '2025-09-26')
    fridays = {d('2025-09-05'), d('2025-09-12'), d('2025-09-19'), d('2025-09-26')}
    rows = (daily_rows('FRI', cal, fridays | {d('2025-09-01')})
            + daily_rows('OK', cal, set()))
    metrics = build_student_metrics(rows, student_ids={'FRI', 'OK', 'GHOST'})

    fri = metrics['FRI']
    assert fri['days_enrolled'] == 20 and fri['days_absent'] == 5
    assert fri['tier'] == 'severe'            # 25% of enrolled days
    assert fri['mon_fri_flag'] is True
    assert abs(fri['attendance_rate'] - 0.75) < 1e-9

    ok = metrics['OK']
    assert ok['tier'] == 'satisfactory' and ok['mon_fri_flag'] is False

    ghost = metrics['GHOST']                   # on caseload, no attendance data
    assert ghost['tier'] is None and ghost['attendance_rate'] is None
    assert ghost['trend'] == 'insufficient'


def test_assembly_fills_unlisted_days_for_the_synergy_pivot_shape():
    """The app's Synergy attendance import lists a day only when the student
    has SOME mark on it, but emits present rows for the other periods of
    listed days. A present-share test therefore looks 'full' while whole
    days are still missing — enrolled days must come from the school
    calendar, not from the student's listed days."""
    cal = _bdate_range('2025-09-08', '2025-09-19')       # 10 school days
    rows = []
    # B is marked (tardy) every day -> establishes the full calendar.
    for day in cal:
        for period in range(1, 7):
            rows.append(row('B', day, 'tardy' if period == 1 else 'present',
                            period=period))
    # A appears on only 2 days: absent all periods on one, one cut on another.
    for period in range(1, 7):
        rows.append(row('A', cal[0], 'absent', period=period))
        rows.append(row('A', cal[3], 'absent' if period == 2 else 'present',
                        period=period))

    metrics = build_student_metrics(rows)
    a = metrics['A']
    assert a['days_enrolled'] == 10, 'unlisted days must count as enrolled'
    assert a['days_absent'] == 1, 'one full absent day; the single cut is partial'
    assert a['tier'] == 'chronic'          # 1/10 = exactly 10%
    assert metrics['B']['days_enrolled'] == 10
    assert metrics['B']['days_absent'] == 0


def test_summarize_population_chronic_share():
    cal = _bdate_range('2025-09-01', '2025-09-26')
    rows = (daily_rows('S1', cal, set())
            + daily_rows('S2', cal, {d('2025-09-01'), d('2025-09-02'),
                                     d('2025-09-03'), d('2025-09-04')}))
    summary = summarize_population(build_student_metrics(rows))
    assert summary['n_students'] == 2
    assert summary['pct_chronic_or_worse'] == 50.0      # S2: 4/20 = 20% severe
    assert summary['tier_counts']['severe'] == 1
    assert abs(summary['mean_attendance_rate'] - 0.9) < 1e-9


# ── corrections the adversarial review forced ──

def test_mixed_daily_and_period_students_keep_their_own_day_size():
    """A student imported as ONE daily row per day sits in the same database
    as six-period Synergy rows. A global periods-per-day floor of 6 would
    turn their fully absent day into 'one period of six' — a partial."""
    day = d('2025-09-08')
    rows = [row('DAILY', day, 'absent')]                       # whole-day record
    rows += [row('PER', day, 'absent', period=p) for p in range(1, 7)]
    metrics = build_student_metrics(rows)
    assert metrics['DAILY']['days_absent'] == 1, \
        'daily student diluted by the period-level schedule size'
    assert metrics['PER']['days_absent'] == 1


def test_activity_and_office_excused_are_present_like():
    """The district's own report excludes Activity and Office Excused from
    Total Absences, but the Synergy import stores them as status 'excused'.
    Counting them as missed days would call a student chronic for going on
    field trips. The original value survives in `reason`."""
    from app.utils.attendance_analysis import categorize

    assert categorize('excused', 'Activity') == 'other_present'
    assert categorize('excused', 'Office Excused') == 'other_present'
    # A real excused absence still counts as missed.
    assert categorize('excused', 'Illness') == 'absent_excused'
    assert categorize('excused', None) == 'absent_excused'
    # And it flows through the day math: an all-Activity day is present.
    day = d('2025-09-08')
    rows = [SimpleNamespace(student_id='A', date=day, period=p,
                            status='excused', reason='Activity')
            for p in range(1, 7)]
    days = build_day_status(rows)
    assert not days[('A', day)]['is_absent_day']
    assert days[('A', day)]['dominant_status'] == 'present'


def test_enrollment_start_clamps_the_present_fill():
    """A January enrollee must not be presumed present since August — that
    dilutes their absence percentage below its real value."""
    from app.utils.attendance_analysis import build_bundle

    cal = _bdate_range('2025-09-08', '2025-09-19')             # 10 school days
    rows = [row('NEW', day, 'absent') for day in cal[5:7]]     # enrolled late
    other = daily_rows('OLD', cal, set())
    bundle = build_bundle(rows + other, enrollment_starts={'NEW': cal[5]})
    new = bundle['metrics']['NEW']
    assert new['days_enrolled'] == 5, \
        f"pre-enrollment days counted: {new['days_enrolled']}"
    assert new['days_absent'] == 2
    assert new['tier'] == 'severe'                             # 2/5 = 40%
    assert bundle['metrics']['OLD']['days_enrolled'] == 10
