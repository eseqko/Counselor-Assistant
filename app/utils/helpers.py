from datetime import datetime, date


def current_school_year(today=None):
    """Return the current school year as 'YYYY-YYYY' (e.g. '2025-2026').

    Months July-December → year/year+1. January-June → year-1/year.
    """
    today = today or date.today()
    yr = today.year if today.month >= 7 else today.year - 1
    return f"{yr}-{yr + 1}"


def current_quarter(today=None):
    """Approximate the current academic quarter (1-4) by calendar date.

    California secondary calendar (rough):
      Q1: Aug 15 - Oct 31
      Q2: Nov 1  - Jan 31  (semester 1 closes after Q2)
      Q3: Feb 1  - Apr 15
      Q4: Apr 16 - Jul     (semester 2; summer treated as Q4)
    """
    today = today or date.today()
    m, d = today.month, today.day
    if (m == 8 and d >= 15) or m in (9, 10):
        return 1
    if m == 11 or m == 12 or m == 1:
        return 2
    if m == 2 or m == 3 or (m == 4 and d <= 15):
        return 3
    return 4


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
