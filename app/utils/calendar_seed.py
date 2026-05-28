"""Seed Jefferson Union HSD school calendars (2026-2030).

Authoritative quarter/semester windows transcribed from the district's
adopted calendar PDFs. Each quarter's `end` is the last day of its second
reporting period; `final_due` is the end-of-quarter grades-due date (blank
on the 2026-2027 sheet). Seeded once if absent; counselors can edit or delete
any year through Settings → School Calendars, and other districts can replace
them entirely.
"""
import json

# (school_year, first_day, last_day,
#  quarters: [(n, start, end, progress_due, final_due)],
#  semesters: [(n, start, end, final_due)])
SEED_CALENDARS = [
    (
        "2026-2027", "2026-08-06", "2027-05-28",
        [
            (1, "2026-08-06", "2026-10-09", None, None),
            (2, "2026-10-13", "2026-12-18", None, None),
            (3, "2027-01-04", "2027-03-12", None, None),
            (4, "2027-03-15", "2027-05-28", None, None),
        ],
        [
            (1, "2026-08-06", "2026-12-18", None),
            (2, "2027-01-04", "2027-05-28", None),
        ],
    ),
    (
        "2027-2028", "2027-08-05", "2028-05-26",
        [
            (1, "2027-08-05", "2027-10-08", "2027-09-09", "2027-10-14"),
            (2, "2027-10-12", "2027-12-17", "2027-11-10", "2028-01-05"),
            (3, "2028-01-03", "2028-03-10", "2028-02-09", "2028-03-15"),
            (4, "2028-03-13", "2028-05-26", "2028-04-26", "2028-06-01"),
        ],
        [
            (1, "2027-08-05", "2027-12-17", "2028-01-05"),
            (2, "2028-01-03", "2028-05-26", "2028-06-01"),
        ],
    ),
    (
        "2028-2029", "2028-08-08", "2029-05-31",
        [
            (1, "2028-08-08", "2028-10-13", "2028-09-14", "2028-10-18"),
            (2, "2028-10-16", "2028-12-22", "2028-11-15", "2029-01-10"),
            (3, "2029-01-08", "2029-03-16", "2029-02-15", "2029-03-21"),
            (4, "2029-03-19", "2029-05-31", "2029-05-02", "2029-06-05"),
        ],
        [
            (1, "2028-08-08", "2028-12-22", "2029-01-10"),
            (2, "2029-01-08", "2029-05-31", "2029-06-05"),
        ],
    ),
    (
        "2029-2030", "2029-08-08", "2030-05-31",
        [
            (1, "2029-08-08", "2029-10-12", "2029-09-14", "2029-10-17"),
            (2, "2029-10-15", "2029-12-21", "2029-11-15", "2030-01-09"),
            (3, "2030-01-07", "2030-03-15", "2030-02-13", "2030-03-20"),
            (4, "2030-03-18", "2030-05-31", "2030-05-01", "2030-06-05"),
        ],
        [
            (1, "2029-08-08", "2029-12-21", "2030-01-09"),
            (2, "2030-01-07", "2030-05-31", "2030-06-05"),
        ],
    ),
]


def _quarters_json(quarters):
    return json.dumps([
        {'n': n, 'start': start, 'end': end,
         'progress_due': progress_due, 'final_due': final_due}
        for (n, start, end, progress_due, final_due) in quarters
    ])


def _semesters_json(semesters):
    return json.dumps([
        {'n': n, 'start': start, 'end': end, 'final_due': final_due}
        for (n, start, end, final_due) in semesters
    ])


def ensure_calendars_seeded():
    """Insert any seed calendar whose school_year isn't already present.

    Idempotent and non-destructive: never overwrites an existing year (so
    counselor edits and PDF uploads survive). Safe to call on every boot.
    """
    from datetime import date
    from app import db
    from app.models.school_calendar import SchoolCalendar

    existing = {row.school_year for row in SchoolCalendar.query.all()}
    added = 0
    for (sy, first_day, last_day, quarters, semesters) in SEED_CALENDARS:
        if sy in existing:
            continue
        cal = SchoolCalendar(
            school_year=sy,
            first_day=date.fromisoformat(first_day),
            last_day=date.fromisoformat(last_day),
            quarters_json=_quarters_json(quarters),
            semesters_json=_semesters_json(semesters),
            source='seed',
        )
        db.session.add(cal)
        added += 1
    if added:
        db.session.commit()
    return added
