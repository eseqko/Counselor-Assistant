"""Attendance analysis: tiers, streaks, patterns, trends, breakdowns.

Ported from the counselor's standalone Attendance Tracker
(github.com/eseqko/attendancetracker, src/attendance_tracker/metrics.py and
friends) so both tools agree number-for-number. Every threshold and formula
here mirrors that codebase — the source is cited per function — and the unit
tests pin the same expected values its test suite pins. Pure Python over
AttendanceRecord-shaped rows; no pandas.

Vocabulary bridge: AttendanceRecord.status is already categorized, so the
tracker's code-mapping wizard has no job here.

    present -> present        absent -> absent_unexcused
    excused -> absent_excused tardy  -> tardy

Two shapes of imported data are handled, mirroring the tracker's Shape logic:

* **Full reports** — a row for every (student, day[, period]), present
  included. Day counts fall straight out.
* **Exception reports** (e.g. Synergy ATP201) — only days WITH marks appear,
  and only the marked periods of those days. Two denominators are then wrong:
  periods-per-day (one cut must not count as a full absent day) and enrolled
  days (an unlisted day means PRESENT). ``densify_day_status`` corrects both,
  exactly as the tracker's densify does. ``is_exception_report`` decides which
  shape the data is, from the share of present-like rows.
"""
from collections import defaultdict
from datetime import timedelta

# ── Categories (tracker: constants.py Category / ABSENT_CATEGORIES) ──────────

PRESENT = 'present'
ABSENT_UNEXCUSED = 'absent_unexcused'
ABSENT_EXCUSED = 'absent_excused'
TARDY = 'tardy'
OTHER_PRESENT = 'other_present'
UNKNOWN = 'unknown'
PARTIAL = 'partial'                     # dominant_status for sub-threshold days

ABSENT_CATEGORIES = frozenset({ABSENT_EXCUSED, ABSENT_UNEXCUSED})
PRESENT_LIKE_CATEGORIES = frozenset({PRESENT, OTHER_PRESENT, TARDY})

#: AttendanceRecord.status -> category.
STATUS_CATEGORY = {
    'present': PRESENT,
    'absent': ABSENT_UNEXCUSED,
    'excused': ABSENT_EXCUSED,
    'tardy': TARDY,
}

#: Reasons whose "excused" rows are really present-like. The district's own
#: attendance report excludes Activity and Office Excused from Total Absences
#: (verified against that report in the tracker: constants.py, ACT/OFF), but
#: this app's Synergy import stores them as status 'excused' — counting them
#: as missed days would call a student chronically absent for going on field
#: trips. The original Synergy value survives in AttendanceRecord.reason, so
#: the correction needs no reimport.
_PRESENT_LIKE_REASONS = frozenset({'activity', 'office excused', 'office ex'})


def categorize(status, reason=None):
    cat = STATUS_CATEGORY.get((status or '').strip().lower(), UNKNOWN)
    if (cat == ABSENT_EXCUSED
            and (reason or '').strip().lower() in _PRESENT_LIKE_REASONS):
        return OTHER_PRESENT
    return cat


def _cat(row):
    """Category for an AttendanceRecord-shaped row (reason optional)."""
    return categorize(row.status, getattr(row, 'reason', None))


# ── Thresholds (tracker: constants.py — values identical) ────────────────────

#: Federal ">=50% of the day" convention for counting a day absent.
ABSENT_DAY_THRESHOLD = 0.5

#: Tier ladder lower bounds, in percent of enrolled days missed.
TIERS = ('satisfactory', 'at_risk', 'chronic', 'severe')
TIER_LABELS = {
    'satisfactory': 'Satisfactory (<5%)',
    'at_risk': 'At risk (5–9%)',
    'chronic': 'Chronic (10–19%)',
    'severe': 'Severe (≥20%)',
}

#: Weekly-trend classification: least-squares slope of the weekly attendance
#: rate over the last TREND_WINDOW_WEEKS; +/-TREND_SLOPE_CUTOFF (rate units
#: per week, i.e. 0.5pp) splits improving/stable/declining.
TREND_SLOPE_CUTOFF = 0.005
TREND_WINDOW_WEEKS = 6
TREND_MIN_WEEKS = 4

#: Monday/Friday pattern: Mon or Fri absence rate >= this multiple of the
#: Tue-Thu mean, with at least MIN_ABSENCES_FOR_DOW_FLAG absences in total.
DOW_FLAG_RATIO = 1.5
MIN_ABSENCES_FOR_DOW_FLAG = 5

#: Period skipping: a period's unexcused-miss rate >= this multiple of the
#: mean of the student's OTHER periods, with at least this many misses.
PERIOD_SKIP_RATIO = 2.0
PERIOD_SKIP_MIN_COUNT = 3

#: Below this share of present-like rows, the data is an absences-only
#: exception export and enrolled days cannot be counted from it directly.
EXCEPTION_REPORT_PRESENT_SHARE = 0.05


# ── Day status (tracker: metrics.build_day_status) ───────────────────────────


def build_day_status(rows, absent_day_threshold=ABSENT_DAY_THRESHOLD):
    """Collapse attendance rows to one record per (student, date).

    ``rows`` — objects with .student_id, .date, .status (period irrelevant
    here: every row is one scheduled slot, daily rows simply have one).

    Returns {(student_id, date): day} where day has periods_scheduled/absent/
    excused/unexcused/tardy, is_absent_day, is_partial, is_tardy_day and
    dominant_status. A day is absent when the absent share of its scheduled
    slots reaches the threshold; dominant_status prefers unexcused on ties.
    """
    days = {}
    for r in rows:
        key = (r.student_id, r.date)
        d = days.get(key)
        if d is None:
            d = days[key] = {
                'student_id': r.student_id, 'date': r.date,
                'periods_scheduled': 0, 'periods_absent': 0,
                'periods_excused': 0, 'periods_unexcused': 0,
                'periods_tardy': 0,
            }
        cat = _cat(r)
        d['periods_scheduled'] += 1
        if cat in ABSENT_CATEGORIES:
            d['periods_absent'] += 1
            if cat == ABSENT_EXCUSED:
                d['periods_excused'] += 1
            else:
                d['periods_unexcused'] += 1
        elif cat == TARDY:
            d['periods_tardy'] += 1
    for d in days.values():
        _flag_day(d, absent_day_threshold)
    return days


def _flag_day(d, threshold):
    scheduled = d['periods_scheduled'] or 1
    absent = d['periods_absent']
    d['is_absent_day'] = absent / scheduled >= threshold
    d['is_partial'] = absent > 0 and not d['is_absent_day']
    d['is_tardy_day'] = d['periods_tardy'] > 0
    if d['is_absent_day']:
        d['dominant_status'] = (
            ABSENT_UNEXCUSED if d['periods_unexcused'] >= d['periods_excused']
            else ABSENT_EXCUSED)
    elif d['is_partial']:
        d['dominant_status'] = PARTIAL
    elif d['is_tardy_day']:
        d['dominant_status'] = TARDY
    else:
        d['dominant_status'] = PRESENT


def school_calendar(rows):
    """Sorted distinct dates across all given rows — the school-day calendar."""
    return sorted({r.date for r in rows if r.date is not None})


def present_like_share(rows):
    total = marked = 0
    for r in rows:
        total += 1
        if _cat(r) in PRESENT_LIKE_CATEGORIES:
            marked += 1
    return (marked / total) if total else 0.0


def is_exception_report(rows):
    """True when almost nothing is present-like — an absences-only export.

    Tracker: metrics.is_exception_report. On such data, distinct dates are NOT
    enrolled days and single marks are NOT whole days; densify first.
    """
    return present_like_share(rows) < EXCEPTION_REPORT_PRESENT_SHARE


def infer_periods_per_day(rows):
    """Largest number of marks any student has on one date (tracker ditto)."""
    counts = defaultdict(int)
    for r in rows:
        counts[(r.student_id, r.date)] += 1
    return max(counts.values(), default=1)


def densify_day_status(days, periods_per_day, calendar, student_ids,
                       absent_day_threshold=ABSENT_DAY_THRESHOLD,
                       start_by_student=None):
    """Correct exception-report day statuses (tracker: densify_day_status).

    Re-flags marked days against ``periods_per_day`` (so one cut period is a
    partial, not a full absent day) and adds a PRESENT day for every
    (student, calendar day) pair with no marks at all.

    ``periods_per_day`` — an int applied to everyone, or {student_id: int}.
    The per-student form exists for MIXED data: a student imported as one
    daily row per day must be floored at 1, or the schoolwide floor of 6
    turns their whole absent day into "one period of six" — a partial.

    ``start_by_student`` — optional {student_id: date}: present-fill starts
    there instead of the calendar start, so a mid-year enrollee isn't
    presumed present for months they weren't enrolled (which would dilute
    their tier). Marked days are always kept regardless.
    """
    def floor_for(sid):
        if isinstance(periods_per_day, dict):
            return int(periods_per_day.get(sid, 1))
        return int(periods_per_day)

    starts = start_by_student or {}
    fixed = {}
    for key, d in days.items():
        d = dict(d)
        d['periods_scheduled'] = max(d['periods_scheduled'],
                                     floor_for(d['student_id']))
        _flag_day(d, absent_day_threshold)
        fixed[key] = d
    for sid in student_ids:
        start = starts.get(sid)
        for day in calendar:
            if start and day < start:
                continue
            key = (sid, day)
            if key not in fixed:
                fixed[key] = {
                    'student_id': sid, 'date': day,
                    'periods_scheduled': floor_for(sid),
                    'periods_absent': 0, 'periods_excused': 0,
                    'periods_unexcused': 0, 'periods_tardy': 0,
                    'is_absent_day': False, 'is_partial': False,
                    'is_tardy_day': False, 'dominant_status': PRESENT,
                }
    return fixed


# ── Per-student counts and tiers (tracker: per_student_counts, tier_for) ─────


def per_student_counts(days):
    """{sid: {days_enrolled, days_absent, days_excused, days_unexcused,
    days_tardy}}. Excused/unexcused split ABSENT DAYS by dominant status."""
    out = defaultdict(lambda: {
        'days_enrolled': 0, 'days_absent': 0, 'days_excused': 0,
        'days_unexcused': 0, 'days_tardy': 0,
    })
    for d in days.values():
        c = out[d['student_id']]
        c['days_enrolled'] += 1
        if d['is_absent_day']:
            c['days_absent'] += 1
            if d['dominant_status'] == ABSENT_EXCUSED:
                c['days_excused'] += 1
            else:
                c['days_unexcused'] += 1
        if d['is_tardy_day']:
            c['days_tardy'] += 1
    return dict(out)


def tier_for(days_absent, days_enrolled):
    """Chronic-absenteeism tier. Integer cross-multiplication, so boundary
    cases like 9 of 180 (exactly 5%) land on their tier with no float drift.
    Tracker: metrics.tier_for — boundaries 5 / 10 / 20 percent."""
    if not days_enrolled or days_enrolled <= 0:
        return None
    scaled = days_absent * 100
    if scaled >= 20 * days_enrolled:
        return 'severe'
    if scaled >= 10 * days_enrolled:
        return 'chronic'
    if scaled >= 5 * days_enrolled:
        return 'at_risk'
    return 'satisfactory'


# ── Streaks (tracker: compute_streaks) ───────────────────────────────────────


def compute_streaks(days, calendar):
    """{sid: {'current': n, 'max': n}} — runs of absent days in school-day
    index space, so weekends and breaks never interrupt a streak. ``current``
    is the run ending on the LAST calendar day (0 if they attended it)."""
    pos = {day: i for i, day in enumerate(calendar)}
    n_days = len(calendar)
    absent_positions = defaultdict(list)
    students = set()
    for d in days.values():
        students.add(d['student_id'])
        if d['is_absent_day'] and d['date'] in pos:
            absent_positions[d['student_id']].append(pos[d['date']])

    out = {sid: {'current': 0, 'max': 0} for sid in students}
    for sid, positions in absent_positions.items():
        positions = sorted(set(positions))
        longest = run = 1
        for prev, cur in zip(positions, positions[1:]):
            run = run + 1 if cur == prev + 1 else 1
            longest = max(longest, run)
        out[sid]['max'] = longest
        if n_days and positions[-1] == n_days - 1:
            out[sid]['current'] = run
    return out


# ── Day-of-week patterns (tracker: weekday_rates, mon_fri_flags) ─────────────


def weekday_rates(days):
    """{sid: {weekday: {'enrolled': n, 'absent': n}}} over all weekdays."""
    out = defaultdict(lambda: defaultdict(lambda: {'enrolled': 0, 'absent': 0}))
    for d in days.values():
        cell = out[d['student_id']][d['date'].weekday()]
        cell['enrolled'] += 1
        if d['is_absent_day']:
            cell['absent'] += 1
    return {sid: dict(wd) for sid, wd in out.items()}


def mon_fri_flag(per_weekday):
    """Monday/Friday absence pattern for ONE student's weekday map.

    Tracker: mon_fri_flags — flag when Mon or Fri rate reaches DOW_FLAG_RATIO
    times the Tue-Thu mean and total absences reach the minimum; when the
    midweek mean is 0 the ratio degenerates, so any positive Mon/Fri rate
    qualifies instead.
    """
    def rate(wd):
        cell = per_weekday.get(wd)
        return (cell['absent'] / cell['enrolled']) if cell and cell['enrolled'] else 0.0

    total_absences = sum(c['absent'] for c in per_weekday.values())
    if total_absences < MIN_ABSENCES_FOR_DOW_FLAG:
        return False
    monday, friday = rate(0), rate(4)
    mid = [rate(wd) for wd in (1, 2, 3) if per_weekday.get(wd, {}).get('enrolled')]
    midweek = sum(mid) / len(mid) if mid else 0.0
    if midweek > 0:
        return monday >= DOW_FLAG_RATIO * midweek or friday >= DOW_FLAG_RATIO * midweek
    return monday > 0 or friday > 0


# ── Weekly rates and trends (tracker: weekly_rates, compute_trends) ──────────


def week_start(day):
    """Monday of the week containing ``day`` (pandas W-period start)."""
    return day - timedelta(days=day.weekday())


def weekly_rates(days):
    """{sid: [(week_start, school_days, absent_days, rate), ...]} sorted by
    week; rate is the attendance rate 1 - absent/school_days."""
    agg = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for d in days.values():
        cell = agg[d['student_id']][week_start(d['date'])]
        cell[0] += 1
        if d['is_absent_day']:
            cell[1] += 1
    out = {}
    for sid, weeks in agg.items():
        out[sid] = [
            (week, school, absent, 1 - absent / school)
            for week, (school, absent) in sorted(weeks.items()) if school > 0
        ]
    return out


def _least_squares_slope(values):
    """Slope of the ordinary least-squares line through (0..n-1, values)."""
    n = len(values)
    xs = range(n)
    sum_x = sum(xs)
    sum_y = sum(values)
    sum_xy = sum(x * y for x, y in zip(xs, values))
    sum_xx = sum(x * x for x in xs)
    denom = n * sum_xx - sum_x * sum_x
    if denom == 0:
        return 0.0
    return (n * sum_xy - sum_x * sum_y) / denom


def compute_trend(weekly, window_weeks=TREND_WINDOW_WEEKS,
                  min_weeks=TREND_MIN_WEEKS):
    """('improving'|'stable'|'declining'|'insufficient', slope_pp_per_week).

    Tracker: compute_trends — least-squares slope of the weekly rate over the
    student's last ``window_weeks`` weeks; slope*100 is pp/week; below
    ``min_weeks`` weeks the trend is 'insufficient' with a None slope.
    """
    rates = [w[3] for w in weekly][-window_weeks:]
    if len(rates) < max(min_weeks, 2):
        return 'insufficient', None
    slope = _least_squares_slope(rates)
    if slope >= TREND_SLOPE_CUTOFF:
        label = 'improving'
    elif slope <= -TREND_SLOPE_CUTOFF:
        label = 'declining'
    else:
        label = 'stable'
    return label, slope * 100.0


# ── Period skipping (tracker: period_table, period_skips) ────────────────────


def period_table(rows, sessions=None):
    """{sid: {period: {'scheduled': n, 'unexcused': n, 'rate': r}}} from
    period-level rows only. ``sessions`` (school days so far) becomes the
    denominator floor for exception reports, where mark counts alone are not
    a denominator."""
    out = defaultdict(lambda: defaultdict(lambda: {'scheduled': 0, 'unexcused': 0}))
    for r in rows:
        if r.period is None:
            continue
        cell = out[r.student_id][r.period]
        cell['scheduled'] += 1
        if _cat(r) == ABSENT_UNEXCUSED:
            cell['unexcused'] += 1
    table = {}
    for sid, periods in out.items():
        table[sid] = {}
        for period, cell in periods.items():
            scheduled = cell['scheduled']
            if sessions is not None:
                scheduled = max(int(sessions), scheduled)
            table[sid][period] = {
                'scheduled': scheduled,
                'unexcused': cell['unexcused'],
                'rate': cell['unexcused'] / scheduled if scheduled else 0.0,
            }
    return table


def period_skips(table):
    """{sid: worst_period or None} — the period where unexcused misses
    concentrate. Qualifies at PERIOD_SKIP_MIN_COUNT misses AND a rate at
    least PERIOD_SKIP_RATIO times the mean of the student's OTHER periods
    (0 for a single-period student). Highest rate wins; equal rates break
    to the LOWEST period — the tracker sorts by rate descending with a
    stable sort over a period-ordered table, so the first-listed period
    survives its drop_duplicates. The differential harness caught this
    port breaking ties toward the highest period instead."""
    out = {}
    for sid, periods in table.items():
        qualifying = []
        rates = {p: c['rate'] for p, c in periods.items()}
        n = len(rates)
        total = sum(rates.values())
        for period, cell in periods.items():
            other_mean = ((total - cell['rate']) / (n - 1)) if n > 1 else 0.0
            if (cell['unexcused'] >= PERIOD_SKIP_MIN_COUNT
                    and cell['rate'] >= PERIOD_SKIP_RATIO * other_mean):
                qualifying.append((-cell['rate'], period))
        out[sid] = str(min(qualifying)[1]) if qualifying else None
    return out


# ── Breakdowns (tracker: breakdowns.by_weekday / by_month / by_period) ───────

WEEKDAY_NAMES = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday')


def by_weekday(days):
    """Weekday (Mon-Fri) -> enrolled/absent/tardy days and rates."""
    agg = {wd: {'enrolled': 0, 'absent': 0, 'tardy': 0} for wd in range(5)}
    for d in days.values():
        wd = d['date'].weekday()
        if wd >= 5:
            continue
        agg[wd]['enrolled'] += 1
        if d['is_absent_day']:
            agg[wd]['absent'] += 1
        if d['is_tardy_day']:
            agg[wd]['tardy'] += 1
    out = []
    for wd in range(5):
        cell = agg[wd]
        enrolled = cell['enrolled']
        out.append({
            'weekday': WEEKDAY_NAMES[wd],
            'enrolled_days': enrolled, 'absent_days': cell['absent'],
            'tardy_days': cell['tardy'],
            'absence_rate': cell['absent'] / enrolled if enrolled else 0.0,
            'tardy_rate': cell['tardy'] / enrolled if enrolled else 0.0,
        })
    return out


def by_month(days):
    """Month (first-of-month date) -> enrolled/absent/tardy days and rates."""
    agg = defaultdict(lambda: {'enrolled': 0, 'absent': 0, 'tardy': 0})
    for d in days.values():
        month = d['date'].replace(day=1)
        agg[month]['enrolled'] += 1
        if d['is_absent_day']:
            agg[month]['absent'] += 1
        if d['is_tardy_day']:
            agg[month]['tardy'] += 1
    out = []
    for month in sorted(agg):
        cell = agg[month]
        out.append({
            'month': month,
            'enrolled_days': cell['enrolled'], 'absent_days': cell['absent'],
            'tardy_days': cell['tardy'],
            'absence_rate': cell['absent'] / cell['enrolled'],
            'tardy_rate': cell['tardy'] / cell['enrolled'],
        })
    return out


def by_period(rows):
    """Period -> unexcused/excused/tardy counts and distinct students hit."""
    agg = defaultdict(lambda: {'unexcused': 0, 'excused': 0, 'tardies': 0,
                               'students': set()})
    for r in rows:
        if r.period is None:
            continue
        cat = _cat(r)
        if cat not in (ABSENT_UNEXCUSED, ABSENT_EXCUSED, TARDY):
            continue
        cell = agg[r.period]
        if cat == ABSENT_UNEXCUSED:
            cell['unexcused'] += 1
        elif cat == ABSENT_EXCUSED:
            cell['excused'] += 1
        else:
            cell['tardies'] += 1
        cell['students'].add(r.student_id)
    return [{
        'period': period,
        'unexcused': agg[period]['unexcused'],
        'excused': agg[period]['excused'],
        'tardies': agg[period]['tardies'],
        'students': len(agg[period]['students']),
    } for period in sorted(agg)]


# ── Assembly ─────────────────────────────────────────────────────────────────


def build_bundle(rows, student_ids=None, calendar=None, enrollment_starts=None):
    """Metrics plus the shared intermediates a report page needs.

    Returns {'metrics', 'days', 'calendar', 'weekly', 'rows'} so caseload-level
    breakdowns (by_weekday / by_month) and per-student charts draw from the
    SAME densified day map the tiers were computed from — two derivations
    would eventually disagree.

    ``calendar`` — school days known from a WIDER population than ``rows``.
    A single student's marked days are not the school calendar: analyzing one
    student without this would treat their unlisted days as non-days instead
    of as present days.
    """
    rows = list(rows)
    metrics, days, cal, weekly = _assemble(rows, student_ids, calendar,
                                           enrollment_starts)
    return {'metrics': metrics, 'days': days, 'calendar': cal,
            'weekly': weekly, 'rows': rows}


def build_student_metrics(rows, student_ids=None):
    """Everything above, assembled per student — the tracker's metrics frame.

    ``rows`` — AttendanceRecord-shaped rows for the population to analyze
    (one counselor's caseload, or the whole school for a baseline).
    ``student_ids`` — include these even with no rows (metrics all None).

    Exception-shaped data (absences-only) is detected and densified against
    the calendar exactly as the tracker does, so enrolled days and absent-day
    flags stay honest either way.
    """
    return _assemble(list(rows), student_ids)[0]


def _assemble(rows, student_ids=None, calendar=None, enrollment_starts=None):
    calendar = sorted(set(calendar or []) | set(school_calendar(rows)))
    days = build_day_status(rows)
    sessions = None
    if rows:
        # ALWAYS densify, mirroring the tracker's ATP201 (period-wide) path.
        # The Synergy attendance report this app imports lists a day only when
        # the student has some mark on it — present rows exist for the other
        # periods of LISTED days, so a present-share test looks "full" while
        # unlisted days are still missing. Densify fills those as present and
        # floors periods-per-day, and is a no-op on genuinely full data.
        # Students are filled only across days they could plausibly attend:
        # zero-row students stay "no data" rather than perfect attendance,
        # matching the tracker's default (assume_perfect_attendance off).
        #
        # The floor is PER STUDENT: the tracker's global floor is safe there
        # because one uploaded file has one shape, but this database mixes
        # imports — a student recorded as one daily row per day sits beside
        # six-period Synergy rows, and a global floor of 6 would turn that
        # student's fully absent day into "one period of six", a partial.
        global_ppd = infer_periods_per_day(
            [r for r in rows if r.period is not None]) or 1
        daily_only = {r.student_id for r in rows} - {
            r.student_id for r in rows if r.period is not None}
        ppd_by_sid = {r.student_id: (1 if r.student_id in daily_only
                                     else global_ppd) for r in rows}
        days = densify_day_status(days, ppd_by_sid, calendar,
                                  set(ppd_by_sid),
                                  start_by_student=enrollment_starts)
        sessions = len(calendar)

    counts = per_student_counts(days)
    streaks = compute_streaks(days, calendar)
    dow = weekday_rates(days)
    weekly = weekly_rates(days)
    skips = period_skips(period_table(rows, sessions=sessions))

    all_ids = set(counts) | set(student_ids or [])
    out = {}
    for sid in all_ids:
        c = counts.get(sid)
        if not c or not c['days_enrolled']:
            out[sid] = {
                'days_enrolled': 0, 'days_absent': 0, 'days_excused': 0,
                'days_unexcused': 0, 'days_tardy': 0,
                'attendance_rate': None, 'absence_pct': None, 'tier': None,
                'current_streak': 0, 'max_streak': 0,
                'trend': 'insufficient', 'trend_slope': None,
                'mon_fri_flag': False, 'worst_period': None,
            }
            continue
        enrolled, absent = c['days_enrolled'], c['days_absent']
        trend, slope = compute_trend(weekly.get(sid, []))
        streak = streaks.get(sid, {'current': 0, 'max': 0})
        out[sid] = {
            **c,
            'attendance_rate': 1 - absent / enrolled,
            'absence_pct': 100 * absent / enrolled,
            'tier': tier_for(absent, enrolled),
            'current_streak': streak['current'],
            'max_streak': streak['max'],
            'trend': trend, 'trend_slope': slope,
            'mon_fri_flag': mon_fri_flag(dow.get(sid, {})),
            'worst_period': skips.get(sid),
        }
    return out, days, calendar, weekly


def calendar_heatmap(days, calendar, student_id):
    """One student's year at a glance (tracker: charts.calendar_heatmap).

    Returns {'weeks': [monday_dates], 'cells': rows} where cells is 5 lists
    (Mon..Fri), each one entry per week: {'status', 'date'} for a school day,
    None where no school day exists in that slot. Weekends are dropped, and
    non-school weekdays (holidays) stay blank rather than reading as present.
    """
    by_date = {d['date']: d['dominant_status'] for d in days.values()
               if d['student_id'] == student_id}
    school = [day for day in calendar if day.weekday() < 5]
    weeks = sorted({week_start(day) for day in school})
    index = {w: i for i, w in enumerate(weeks)}
    cells = [[None] * len(weeks) for _ in range(5)]
    for day in school:
        cells[day.weekday()][index[week_start(day)]] = {
            'status': by_date.get(day),
            'date': day.isoformat(),
        }
    return {'weeks': [w.isoformat() for w in weeks], 'cells': cells}


def weekly_series(weekly, rolling_weeks=4):
    """Chart-ready weekly rates with a trailing rolling mean (tracker:
    charts.weekly_rate_line, rolling window 4 with min_periods=1)."""
    out = []
    rates = []
    for week, school, absent, rate in weekly:
        rates.append(rate)
        window = rates[-rolling_weeks:]
        out.append({
            'week': week.isoformat(),
            'rate': round(rate * 100, 1),
            'rolling': round(sum(window) / len(window) * 100, 1),
            'school_days': school, 'absent_days': absent,
        })
    return out


def tier_distribution(metrics):
    """{tier: count} over students with a tier, in ladder order."""
    counts = {tier: 0 for tier in TIERS}
    for m in metrics.values():
        if m['tier']:
            counts[m['tier']] += 1
    return counts


def summarize_population(metrics):
    """Cohort aggregates (tracker: cohorts.caseload_vs_baseline row shape)."""
    rated = [m['attendance_rate'] for m in metrics.values()
             if m['attendance_rate'] is not None]
    tiered = [m['tier'] for m in metrics.values() if m['tier']]
    chronic = sum(1 for t in tiered if t in ('chronic', 'severe'))
    return {
        'n_students': len(metrics),
        'n_with_data': len(rated),
        'mean_attendance_rate': sum(rated) / len(rated) if rated else None,
        'pct_chronic_or_worse': 100 * chronic / len(tiered) if tiered else None,
        'tier_counts': tier_distribution(metrics),
    }
