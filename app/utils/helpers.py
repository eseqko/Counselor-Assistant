from datetime import datetime, date


def current_school_year(today=None):
    """Return the current school year as 'YYYY-YYYY' (e.g. '2025-2026').

    Months July-December → year/year+1. January-June → year-1/year.
    """
    today = today or date.today()
    yr = today.year if today.month >= 7 else today.year - 1
    return f"{yr}-{yr + 1}"


def _lookup_calendar(today):
    """Find the SchoolCalendar covering `today`, or None.

    Cached per-request via flask.g so per-student loops don't re-query.
    Safe to call outside an app/request context (returns None).
    """
    try:
        sy = current_school_year(today)
        from flask import g, has_request_context
        if has_request_context():
            cache = getattr(g, '_school_calendar_cache', None)
            if cache is None:
                cache = {}
                g._school_calendar_cache = cache
            if sy in cache:
                return cache[sy]
        from app.models.school_calendar import SchoolCalendar
        cal = SchoolCalendar.for_year(sy)
        if has_request_context():
            g._school_calendar_cache[sy] = cal
        return cal
    except Exception:
        return None


def _quarter_by_date(today):
    """Month-based fallback when no SchoolCalendar row exists for the year.

    Approximate California secondary calendar:
      Q1: Aug 15 - Oct 31
      Q2: Nov 1  - Jan 31
      Q3: Feb 1  - Apr 15
      Q4: Apr 16 - Jul (summer treated as Q4)
    """
    m, d = today.month, today.day
    if (m == 8 and d >= 15) or m in (9, 10):
        return 1
    if m == 11 or m == 12 or m == 1:
        return 2
    if m == 2 or m == 3 or (m == 4 and d <= 15):
        return 3
    return 4


def current_quarter(today=None):
    """Return the current academic quarter (1-4).

    Prefers the district SchoolCalendar for the year; falls back to a
    month-based approximation when no calendar has been configured.
    """
    today = today or date.today()
    cal = _lookup_calendar(today)
    if cal:
        q = cal.quarter_for(today)
        if q:
            return q
    return _quarter_by_date(today)


def current_semester(today=None):
    """Return the current semester (1 = Fall, 2 = Spring).

    Prefers the district SchoolCalendar; falls back to month-based
    (Aug-Dec → 1, Jan-Jul → 2).
    """
    today = today or date.today()
    cal = _lookup_calendar(today)
    if cal:
        s = cal.semester_for(today)
        if s:
            return s
    return 1 if today.month >= 8 or today.month == 12 else 2


def semester_for_quarter(q):
    """Map a quarter number to its semester (Q1/Q2 → 1, Q3/Q4 → 2)."""
    if q in (1, 2):
        return 1
    if q in (3, 4):
        return 2
    return None


def semester_name(n):
    """Human label for a semester number."""
    return {1: 'Fall semester', 2: 'Spring semester'}.get(n, '')


def parse_transcript_quarter(quarter_str):
    """Return (grade_int, quarter_int) from a '10-Q3' string, or (None, None)."""
    if not quarter_str or '-Q' not in quarter_str:
        return None, None
    try:
        g, q = quarter_str.split('-Q')
        return int(g), int(q)
    except (ValueError, AttributeError):
        return None, None


def parse_date(date_str):
    if not date_str:
        return None
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y'):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def parse_time(time_str):
    if not time_str:
        return None
    for fmt in ('%H:%M', '%I:%M %p'):
        try:
            return datetime.strptime(time_str, fmt).time()
        except ValueError:
            continue
    return None
