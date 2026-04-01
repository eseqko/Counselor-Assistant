from datetime import datetime


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
