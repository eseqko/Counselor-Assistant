from datetime import datetime, date


def current_school_year(today=None):
    """Return the current school year as 'YYYY-YYYY' (e.g. '2025-2026').

    Months July-December → year/year+1. January-June → year-1/year.
    """
    today = today or date.today()
    yr = today.year if today.month >= 7 else today.year - 1
    return f"{yr}-{yr + 1}"


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
