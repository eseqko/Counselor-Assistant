"""School-calendar logic: helpers, benchmarks, and the PDF text parser."""
from datetime import date

import pytest

from app.utils.helpers import (current_quarter, current_semester,
                               semester_for_quarter, semester_name,
                               parse_transcript_quarter)
from app.routes.graduation import expected_progress, projected_credits, pace_label


# ---- pure helpers (no DB) -------------------------------------------------

def test_parse_transcript_quarter():
    assert parse_transcript_quarter('10-Q3') == (10, 3)
    assert parse_transcript_quarter('9-Q1') == (9, 1)
    assert parse_transcript_quarter(None) == (None, None)
    assert parse_transcript_quarter('garbage') == (None, None)


def test_semester_for_quarter():
    assert semester_for_quarter(1) == 1
    assert semester_for_quarter(2) == 1
    assert semester_for_quarter(3) == 2
    assert semester_for_quarter(4) == 2
    assert semester_for_quarter(99) is None


def test_semester_name():
    assert semester_name(1) == 'Fall semester'
    assert semester_name(2) == 'Spring semester'
    assert semester_name(None) == ''


def test_expected_progress_grade_and_quarter():
    assert expected_progress(8) is None          # middle school: no HS baseline
    assert expected_progress(13) is None
    # Benchmarks derive from the school's earning capacity (80/yr by default),
    # capped at the 225-credit requirement. These were 90 and 191 when the
    # curve assumed ~55/yr — and 191 at the end of senior year meant a student
    # could clear every benchmark and still be short of graduating.
    assert expected_progress(10, quarter=4)['credits_expected'] == 160
    assert expected_progress(12, quarter=4)['credits_expected'] == 225
    # Q1 expectation is lower than year-end within the same grade
    assert (expected_progress(10, quarter=1)['credits_expected']
            < expected_progress(10, quarter=4)['credits_expected'])


def test_projected_credits():
    assert projected_credits(60, 15) == 75
    assert projected_credits(None, None) == 0


def test_pace_label_wip_aware():
    # Grade 10 Q3 expects 140 credits at an 80/yr pace.
    # 120 completed + 20 WIP projects exactly on pace.
    assert pace_label(120, 20, 10, quarter=3) == 'on pace'
    # without the WIP cushion, behind
    assert pace_label(120, 0, 10, quarter=3) in ('behind pace', 'slightly behind pace')
    # Half-pace is now caught instead of reading as fine.
    assert pace_label(60, 15, 10, quarter=3) == 'critically behind pace' 
    # all-zero is "unknown" (data not posted yet), never "critically behind"
    assert pace_label(0, 0, 9, quarter=1) == 'pace unknown'
    # fresh 9th grader with a full WIP load is fine
    assert pace_label(0, 30, 9, quarter=1) in ('on pace', 'ahead of pace')
    # graduating senior projects ahead
    assert pace_label(200, 25, 12, quarter=4) in ('on pace', 'ahead of pace')


# ---- calendar-aware current_quarter / current_semester (uses seeded data) --

def test_current_quarter_uses_seeded_calendar(app_ctx):
    # 2027-2028 JUHSD calendar is seeded; verify boundaries beat the month guess.
    assert current_quarter(date(2027, 9, 1)) == 1
    assert current_quarter(date(2027, 10, 10)) == 1   # gap after Q1 end -> still Q1
    assert current_quarter(date(2027, 10, 12)) == 2   # Q2 start
    assert current_quarter(date(2028, 1, 15)) == 3
    assert current_quarter(date(2028, 4, 1)) == 4


def test_current_semester_uses_seeded_calendar(app_ctx):
    assert current_semester(date(2027, 11, 20)) == 1   # Fall
    assert current_semester(date(2028, 1, 15)) == 2    # Spring


def test_current_quarter_falls_back_without_calendar(app_ctx):
    # No 2099-2100 calendar exists -> month-based fallback still returns 1-4.
    assert current_quarter(date(2099, 9, 15)) in (1, 2, 3, 4)


def test_seeded_calendars_present(app_ctx):
    from app.models.school_calendar import SchoolCalendar
    years = {c.school_year for c in SchoolCalendar.query.all()}
    assert {'2026-2027', '2027-2028', '2028-2029', '2029-2030'} <= years


# ---- PDF text parser (no external file needed) ----------------------------

# A minimal snippet mirroring the structure of a real JUHSD calendar PDF's
# extracted text (quarter rows interleaved with day counts and due dates).
_SAMPLE = (
    "JEFFERSON UNION HIGH SCHOOL DISTRICT2031-2032 SCHOOL CALENDAR"
    "+ First Day of School - August 4, 2031 - Minimum Day"
    "& Last Day of School - May 28, 2032"
    "FOR SCHOOLS ON QUARTER SCHEDULES"
    "Qtr One 1st Report: Aug 4-Sept 5 22 days Q1 Sept 10"
    "Qtr One 2nd Report: Sept 8-Oct 10 23 days 45 days Oct 15"
    "Qtr Two 1st Report: Oct 14-Nov 7 19 days Q2 Nov 12"
    "Qtr Two 2nd Report: Nov 10-Dec 19 24 days 43 days Jan 7"
    "Qtr Three 1st Report: Jan 5-Feb 6 23 days Q3 Feb 11"
    "Qtr Three 2nd Report: Feb 9-Mar 13 19 days 42 days Mar 18"
    "Qtr Four 1st Report: Mar 16-Apr 24 25 days Q4 Apr 29"
    "Qtr Four 2nd Report: Apr 27-May 28 25 days 50 days June 3"
)


def test_parse_calendar_text_core_fields():
    from app.utils.calendar_parser import parse_calendar_text
    r = parse_calendar_text(_SAMPLE)
    assert r['school_year'] == '2031-2032'
    assert r['first_day'] == date(2031, 8, 4)
    assert r['last_day'] == date(2032, 5, 28)
    assert not r['warnings']

    q = {x['n']: x for x in r['quarters']}
    assert q[1]['start'] == date(2031, 8, 4)
    assert q[1]['end'] == date(2031, 10, 10)
    assert q[1]['progress_due'] == date(2031, 9, 10)
    assert q[1]['final_due'] == date(2031, 10, 15)
    assert q[4]['end'] == date(2032, 5, 28)
    # year inference: spring months roll to the second calendar year
    assert q[3]['start'] == date(2032, 1, 5)


def test_parse_calendar_text_derives_semesters():
    from app.utils.calendar_parser import parse_calendar_text
    r = parse_calendar_text(_SAMPLE)
    s = {x['n']: x for x in r['semesters']}
    # Fall = Q1 start -> Q2 end; Spring = Q3 start -> Q4 end
    assert s[1]['start'] == date(2031, 8, 4)
    assert s[1]['end'] == date(2031, 12, 19)
    assert s[2]['start'] == date(2032, 1, 5)
    assert s[2]['end'] == date(2032, 5, 28)


def test_parse_calendar_text_rejects_unrecognized():
    from app.utils.calendar_parser import parse_calendar_text
    with pytest.raises(ValueError):
        parse_calendar_text("This is not a school calendar at all.")
