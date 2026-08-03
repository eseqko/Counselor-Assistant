"""Synergy GRD401: a grade export with one column PER QUARTER.

The report ships Quarter 1..Quarter 4 as separate columns, with the letter
grade in whichever matches that section's term. The importer expects the long
shape — one row per student per course per quarter — so the wide file has to be
flattened first.

Before that flattening, the header scan picked the FIRST "Quarter N" column it
found and treated the whole file as that one quarter: a full year of grades
imported as Quarter 1 only, about a quarter of the file, with the rest dropped
and nothing said. These tests exist so that cannot come back.
"""
import io

import pytest
from openpyxl import Workbook

from app import db
from app.models.grade import GradeRecord
from app.models.student import Student
from app.models.user import User
from app.routes.data_import._parsers import (
    build_grade_col_map, col, expand_quarter_columns, find_quarter_columns,
    parse_quarter,
)

# The real GRD401 header, in order.
GRD401 = ['Student Name', 'Perm ID', 'Grade', 'Gender', 'Credits Attempted',
          'Credits Completed', 'GPA', 'Period', 'Section ID', 'Course Title',
          'Teacher Name', 'Quarter 1', 'Quarter 2', 'Quarter 3', 'Quarter 4',
          'Credits Att']


def grd_row(perm='STU1', period=1, section='1-100', title='Math Course 1 CP [S1]',
            teacher='Paras, Nikolaos P.', q1='', q2='', q3='', q4='', credits=5):
    return ['Test, Ana', perm, 9, 'M', 80, 80, 3.687, period, section, title,
            teacher, q1, q2, q3, q4, credits]


# ── detecting the wide shape ──

def test_all_four_quarter_columns_are_found():
    assert find_quarter_columns(GRD401) == [(11, 1), (12, 2), (13, 3), (14, 4)]


@pytest.mark.parametrize('header,expected', [
    (['Q1', 'Q2'], [(0, 1), (1, 2)]),
    (['Qtr 3'], [(0, 3)]),
    (['quarter 4'], [(0, 4)]),
    (['Quarter'], []),                 # no digit — not a quarter column
    (['Quarter 5'], []),               # out of range
    (['Credits Att'], []),             # must not match on a substring
])
def test_quarter_header_spellings(header, expected):
    assert find_quarter_columns(header) == expected


# ── the unpivot ──

def test_each_quarter_becomes_its_own_row():
    rows = [grd_row(q1='A'), grd_row(q2='B'), grd_row(q3='C'), grd_row(q4='D')]
    header, out = expand_quarter_columns(GRD401, rows)
    assert len(out) == 4
    cm = build_grade_col_map(header)
    got = [(parse_quarter(col(r, cm, 'mark_name')), col(r, cm, 'grade')) for r in out]
    assert got == [(1, 'A'), (2, 'B'), (3, 'C'), (4, 'D')]


def test_the_four_quarter_columns_are_replaced_by_a_grade_and_a_term():
    header, _ = expand_quarter_columns(GRD401, [grd_row(q1='A')])
    assert 'Quarter 1' not in header and 'Quarter 4' not in header
    assert header[-2:] == ['Letter Grade', 'Mark Name']
    # Everything else survives, in order.
    assert header[:11] == GRD401[:11]
    assert 'Credits Att' in header


def test_a_year_long_row_with_several_quarters_emits_one_row_each():
    header, out = expand_quarter_columns(GRD401, [grd_row(q1='A', q2='B', q4='C')])
    cm = build_grade_col_map(header)
    assert [(parse_quarter(col(r, cm, 'mark_name')), col(r, cm, 'grade')) for r in out] \
        == [(1, 'A'), (2, 'B'), (4, 'C')]


def test_ungraded_quarters_produce_no_rows():
    """A section graded only in Q3 must not create three empty Q1/Q2/Q4 rows."""
    _, out = expand_quarter_columns(GRD401, [grd_row(q3='B-')])
    assert len(out) == 1


def test_a_row_with_no_grades_at_all_is_dropped():
    assert expand_quarter_columns(GRD401, [grd_row()])[1] == []


def test_the_other_columns_ride_along_unchanged():
    header, out = expand_quarter_columns(
        GRD401, [grd_row(perm='STU9', period=4, section='4-033A',
                         title='PE 9 [S1]', teacher='Stewart, Anne C.', q3='B+')])
    cm = build_grade_col_map(header)
    r = out[0]
    assert col(r, cm, 'perm_id') == 'STU9'
    assert col(r, cm, 'period') == '4'
    assert col(r, cm, 'course_title') == 'PE 9 [S1]'
    assert col(r, cm, 'staff_name') == 'Stewart, Anne C.'
    assert col(r, cm, 'course_id') == '4-033A'
    # Per-course credits, not the student's yearly total in 'Credits Attempted'.
    assert col(r, cm, 'credits_att') == '5'


def test_short_rows_do_not_crash_the_unpivot():
    _, out = expand_quarter_columns(GRD401, [['Test, Ana', 'STU1', 9]])
    assert out == []


# ── leaving the existing single-quarter path alone ──

def test_a_single_quarter_export_is_returned_untouched():
    """The older Synergy export names one quarter in the header and relies on
    _quarter_from_header; flattening it would break that path."""
    header = ['Perm ID', 'Course Title', 'Quarter 3']
    rows = [['STU1', 'Math', 'B']]
    assert expand_quarter_columns(header, rows) == (header, rows)
    assert build_grade_col_map(header).get('_quarter_from_header') == 3


def test_a_report_with_no_quarter_columns_is_returned_untouched():
    header = ['Perm ID', 'Course Title', 'Letter Grade', 'Mark Name']
    rows = [['STU1', 'Math', 'B', 'Quarter 2']]
    assert expand_quarter_columns(header, rows) == (header, rows)


def test_the_flattened_file_no_longer_needs_the_header_quarter_fallback():
    """After flattening there IS a real Letter Grade column, so the quarter
    comes per row instead of being assumed for the whole file."""
    header, _ = expand_quarter_columns(GRD401, [grd_row(q2='A')])
    cm = build_grade_col_map(header)
    assert cm.get('_quarter_from_header') is None
    assert 'grade' in cm and 'mark_name' in cm


# ── end to end ──

@pytest.fixture
def grd_env(app):
    with app.app_context():
        User.query.filter_by(username='grd_me').delete(synchronize_session=False)
        Student.query.filter(Student.student_id_number.like('GRD-%')).delete(
            synchronize_session=False)
        db.session.commit()
        me = User(username='grd_me', display_name='GRD Me', role='counselor',
                  setup_completed=True)
        me.set_password('passw0rd123')
        db.session.add(me)
        db.session.commit()
        s = Student(student_id_number='GRD-1', first_name='Ana', last_name='Reyes',
                    grade_level=9, status='active', assigned_counselor_id=me.id)
        db.session.add(s)
        db.session.commit()
        ids = dict(me=me.id, student=s.id)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(ids['me'])
        sess['_fresh'] = True
    yield client, ids

    with app.app_context():
        GradeRecord.query.filter_by(student_id=ids['student']).delete(
            synchronize_session=False)
        Student.query.filter_by(id=ids['student']).delete(synchronize_session=False)
        User.query.filter_by(id=ids['me']).delete(synchronize_session=False)
        db.session.commit()


def _upload(client, rows, year='2025-2026', grade_type='final'):
    wb = Workbook()
    ws = wb.active
    ws.append(GRD401)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return client.post('/data-import/grades/upload', data={
        'file': (buf, 'grd401.xlsx'), 'school_year': year, 'grade_type': grade_type,
    }, content_type='multipart/form-data', follow_redirects=True)


def test_a_full_year_imports_all_four_quarters(app, grd_env):
    """The regression that mattered: this used to import Quarter 1 only."""
    client, ids = grd_env
    _upload(client, [
        grd_row(perm='GRD-1', title='Math Course 1 CP [S1]', section='1-100', q1='A'),
        grd_row(perm='GRD-1', title='Math Course 1 CP [S2]', section='1-101', q2='B'),
        grd_row(perm='GRD-1', title='Spanish 1 CP [S1]', section='1-136', q3='A+'),
        grd_row(perm='GRD-1', title='Spanish 1 CP [S2]', section='1-137', q4='C-'),
    ])
    with app.app_context():
        got = GradeRecord.query.filter_by(student_id=ids['student']).all()
        assert len(got) == 4, f'expected all four quarters, got {len(got)}'
        assert {g.quarter for g in got} == {1, 2, 3, 4}
        assert {g.letter_grade for g in got} == {'A', 'B', 'A+', 'C-'}
        assert all(g.school_year == '2025-2026' for g in got)


def test_the_teacher_name_survives_the_import(app, grd_env):
    """Everything downstream — the staff directory, D/F by teacher — is keyed
    on it, and GRD401 spells the column 'Teacher Name'."""
    client, ids = grd_env
    _upload(client, [grd_row(perm='GRD-1', teacher='King, Arminda', q1='B')])
    with app.app_context():
        g = GradeRecord.query.filter_by(student_id=ids['student']).first()
        assert g is not None and g.teacher == 'King, Arminda'


def test_reimporting_the_same_export_does_not_duplicate(app, grd_env):
    client, ids = grd_env
    rows = [grd_row(perm='GRD-1', q1='A'), grd_row(perm='GRD-1', q2='B')]
    _upload(client, rows)
    _upload(client, rows)
    with app.app_context():
        assert GradeRecord.query.filter_by(student_id=ids['student']).count() == 2


def test_final_grades_supersede_progress_grades_in_every_quarter(app, grd_env):
    """The purge used to key off the single header quarter, so with a
    multi-quarter file the stale progress rows survived in Q2-Q4."""
    client, ids = grd_env
    with app.app_context():
        for q in (1, 2, 3, 4):
            db.session.add(GradeRecord(
                student_id=ids['student'], school_year='2025-2026', quarter=q,
                grade_type='progress', course_name='Math Course 1 CP [S1]',
                period=1, teacher='Paras, Nikolaos P.', letter_grade='F'))
        db.session.commit()
        assert GradeRecord.query.filter_by(grade_type='progress').count() == 4

    _upload(client, [
        grd_row(perm='GRD-1', q1='A'), grd_row(perm='GRD-1', q2='A'),
        grd_row(perm='GRD-1', q3='A'), grd_row(perm='GRD-1', q4='A'),
    ])
    with app.app_context():
        assert GradeRecord.query.filter_by(
            grade_type='progress', school_year='2025-2026').count() == 0
