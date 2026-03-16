from datetime import datetime, date


def format_date(d):
    if isinstance(d, datetime):
        return d.strftime('%m/%d/%Y %I:%M %p')
    if isinstance(d, date):
        return d.strftime('%m/%d/%Y')
    return str(d) if d else ''


def format_time(t):
    if t:
        return t.strftime('%I:%M %p')
    return ''


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
