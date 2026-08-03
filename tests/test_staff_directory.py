"""Building the staff directory from an imported class schedule.

Grounded in the counselor's real Synergy export wherever possible: the traps
here are all real-data traps, not ones a synthetic fixture would suggest.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.utils.staff_directory import (
    apply_staff_records, derive_staff_from_schedule, summarize,
)
from app.utils.schedule_parser import parse_schedule_excel

FIXTURES = Path(__file__).parent / 'fixtures'
SAMPLE_XLS = FIXTURES / 'schedule_sample.xls'
needs_xls = pytest.mark.skipif(not SAMPLE_XLS.exists(), reason='sample .xls absent')


def row(teacher, room='', course='22004', title='Math Course 2 CP', non_class=False):
    return {'teacher_name': teacher, 'room': room, 'course_number': course,
            'course_title': title, 'is_non_class': non_class}


# ── identity ──

def test_a_teacher_seen_many_times_becomes_one_record():
    got = derive_staff_from_schedule([row('Mar, J.', 'E114'), row('Mar, J.', 'E114')])
    assert len(got) == 1
    assert got['mar, j.']['name'] == 'Mar, J.'


def test_names_collapse_case_insensitively_keeping_the_first_spelling():
    """Matches how the grade importer keys staff, so the two never duplicate."""
    got = derive_staff_from_schedule([row('Mar, J.', 'E114'), row('MAR, J.', 'E114')])
    assert list(got) == ['mar, j.']
    assert got['mar, j.']['name'] == 'Mar, J.'


def test_rows_with_no_teacher_are_skipped():
    assert derive_staff_from_schedule([row(''), row('   ')]) == {}


# ── job title, read from the administrative row ──

def test_an_administrative_row_names_the_persons_actual_job():
    """Synergy puts 'Vice Principal' in the course title of a non-class row.
    That row is the only place the SIS says what the person does."""
    got = derive_staff_from_schedule([
        row('Ho, J.', title='Vice Principal', non_class=True)])
    assert got['ho, j.']['title'] == 'Administrator'


def test_an_admin_who_also_supervises_a_class_is_still_an_admin():
    """The real export has Ho, J. as Vice Principal AND supervising a Teacher
    Assistant period. Requiring EVERY row to be administrative would file the
    vice principal as a teacher."""
    got = derive_staff_from_schedule([
        row('Ho, J.', title='Teacher Assistant [S1]'),
        row('Ho, J.', title='Teacher Assistant [S2]'),
        row('Ho, J.', title='Vice Principal', non_class=True),
    ])
    assert got['ho, j.']['title'] == 'Administrator'


@pytest.mark.parametrize('admin_title,expected', [
    ('Vice Principal', 'Administrator'),
    ('Assistant Principal', 'Administrator'),
    ('Principal', 'Administrator'),
    ('Dean', 'Administrator'),
    ('Counselor', 'Counselor'),
])
def test_administrative_titles_map_to_staff_roles(admin_title, expected):
    got = derive_staff_from_schedule([row('X, Y.', title=admin_title, non_class=True)])
    assert got['x, y.']['title'] == expected


def test_an_ordinary_teacher_defaults_to_teacher():
    assert derive_staff_from_schedule([row('Sachs, S.', 'E126')])['sachs, s.']['title'] == 'Teacher'


# ── room and department: only when the data is unambiguous ──

def test_room_is_taken_from_where_the_teacher_actually_teaches():
    got = derive_staff_from_schedule([row('Sachs, S.', 'E126'), row('Sachs, S.', 'E126')])
    assert got['sachs, s.']['room'] == 'E126'


def test_a_teacher_split_evenly_between_two_rooms_gets_none():
    """The real export has Mar, J. in E114 for period 1 and J104 for period 3.
    Picking one would send a counselor to the wrong door."""
    got = derive_staff_from_schedule([row('Mar, J.', 'E114'), row('Mar, J.', 'J104')])
    assert 'room' not in got['mar, j.']


def test_a_clear_majority_room_still_wins():
    got = derive_staff_from_schedule([
        row('Mar, J.', 'E114'), row('Mar, J.', 'E114'), row('Mar, J.', 'J104')])
    assert got['mar, j.']['room'] == 'E114'


def test_an_admin_row_contributes_no_room():
    """A 'Vice Principal' row sits in a period with no room; it must not blank
    out or compete with the room where the person really teaches."""
    got = derive_staff_from_schedule([
        row('Ho, J.', 'B200'),
        row('Ho, J.', '', title='Vice Principal', non_class=True)])
    assert got['ho, j.']['room'] == 'B200'


def test_department_comes_from_the_course_catalog():
    got = derive_staff_from_schedule(
        [row('Sands, K.', 'B103', course='31010')],
        {'31010': 'History/Social Science'})
    assert got['sands, k.']['department'] == 'History/Social Science'


def test_an_unknown_course_yields_no_department_rather_than_a_guess():
    got = derive_staff_from_schedule([row('Sands, K.', 'B103', course='99999')], {})
    assert 'department' not in got['sands, k.']


def test_a_teacher_split_evenly_across_departments_gets_none():
    got = derive_staff_from_schedule(
        [row('Gold, D.', 'C110', course='A'), row('Gold, D.', 'C110', course='B')],
        {'A': 'CTE', 'B': 'Electives'})
    assert 'department' not in got['gold, d.']


# ── upsert: the counselor's own edits are sacred ──

def _staff(name, **kw):
    base = {'name': name, 'title': '', 'room': '', 'department': ''}
    base.update(kw)
    return SimpleNamespace(**base)


def test_new_staff_are_created():
    made = []
    created, enriched = apply_staff_records(
        {'a, b.': {'name': 'A, B.', 'title': 'Teacher', 'room': 'X1'}},
        {}, lambda **f: made.append(f))
    assert created == 1 and enriched == 0
    assert made == [{'name': 'A, B.', 'title': 'Teacher', 'room': 'X1'}]


def test_blank_fields_on_an_existing_record_are_filled_in():
    existing = _staff('Sachs, S.')
    created, enriched = apply_staff_records(
        {'sachs, s.': {'name': 'Sachs, S.', 'title': 'Teacher', 'room': 'E126',
                       'department': 'CTE'}},
        {'sachs, s.': existing}, lambda **f: None)
    assert (created, enriched) == (0, 1)
    assert (existing.room, existing.department, existing.title) == ('E126', 'CTE', 'Teacher')


def test_a_value_the_counselor_typed_is_never_overwritten():
    """The whole point of re-importing safely: a counselor who corrected a room
    must not have the SIS stomp it back on the next upload."""
    existing = _staff('Sachs, S.', room='Portable 3', title='Support Staff')
    created, enriched = apply_staff_records(
        {'sachs, s.': {'name': 'Sachs, S.', 'title': 'Teacher', 'room': 'E126',
                       'department': 'CTE'}},
        {'sachs, s.': existing}, lambda **f: None)
    assert existing.room == 'Portable 3'
    assert existing.title == 'Support Staff'
    assert existing.department == 'CTE'      # this one WAS blank, so it filled
    assert (created, enriched) == (0, 1)


def test_reimporting_an_unchanged_schedule_reports_no_churn():
    existing = _staff('Sachs, S.', title='Teacher', room='E126', department='CTE')
    created, enriched = apply_staff_records(
        {'sachs, s.': {'name': 'Sachs, S.', 'title': 'Teacher', 'room': 'E126',
                       'department': 'CTE'}},
        {'sachs, s.': existing}, lambda **f: None)
    assert (created, enriched) == (0, 0)


def test_whitespace_only_existing_values_count_as_blank():
    existing = _staff('Sachs, S.', room='   ')
    apply_staff_records(
        {'sachs, s.': {'name': 'Sachs, S.', 'title': 'Teacher', 'room': 'E126'}},
        {'sachs, s.': existing}, lambda **f: None)
    assert existing.room == 'E126'


# ── preview summary ──

def test_summary_separates_new_staff_from_known_ones():
    derived = derive_staff_from_schedule([row('Mar, J.', 'E114'), row('Sachs, S.', 'E126')])
    s = summarize(derived, ['mar, j.'])
    assert s['total'] == 2 and s['new_count'] == 1 and s['known_count'] == 1
    assert s['new'] == ['Sachs, S.']


def test_summary_matches_known_names_case_insensitively():
    derived = derive_staff_from_schedule([row('Mar, J.', 'E114')])
    assert summarize(derived, ['MAR, J.'])['new_count'] == 0


# ── against the counselor's real export ──

@needs_xls
def test_the_real_export_yields_the_expected_directory():
    with open(SAMPLE_XLS, 'rb') as f:
        rows = parse_schedule_excel(f)
    got = derive_staff_from_schedule(rows)

    # Eight distinct people across eighteen rows.
    assert len(got) == 8
    assert got['owens, e.']['room'] == 'K101'        # advisory teacher counts
    assert got['sachs, s.']['room'] == 'E126'
    # Mar, J. teaches period 1 in E114 and period 3 in J104 — a genuine tie.
    assert 'room' not in got['mar, j.']
    # Ho, J. is the vice principal who also supervises a TA period.
    assert got['ho, j.']['title'] == 'Administrator'
    # Everyone else is a teacher.
    assert {r['title'] for k, r in got.items() if k != 'ho, j.'} == {'Teacher'}
    assert all(r['name'] for r in got.values())
