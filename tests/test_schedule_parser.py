"""Schedule parsing: Synergy Excel export and the printed first-day PDF.

Both run against the REAL sample files a counselor supplied, because the whole
risk in this feature is misreading a real-world layout. Synthetic fixtures would
have happily passed while the actual export failed.
"""
import io
from pathlib import Path

import pytest

from app.utils.schedule_parser import (
    ParsedRow, classify_title, excel_serial_to_date, normalize_term,
    parse_schedule_excel, parse_schedule_file, parse_schedule_pdf, read_tabular,
    rows_to_parsed,
)

FIXTURES = Path(__file__).parent / 'fixtures'
SAMPLE_XLS = FIXTURES / 'schedule_sample.xls'
SAMPLE_PDF = FIXTURES / 'schedule_sample.pdf'

needs_xls = pytest.mark.skipif(not SAMPLE_XLS.exists(), reason='sample .xls absent')
needs_pdf = pytest.mark.skipif(not SAMPLE_PDF.exists(), reason='sample .pdf absent')


# ── term normalization: the two sources spell things differently ──

@pytest.mark.parametrize('raw,expected', [
    ('Q1', 'Q1'), ('q3', 'Q3'), (' Q 4 ', 'Q4'),
    ('YR', 'YR'),
    ('FALL & SPRING', 'YR'),      # how the printed PDF writes a year-long row
    ('Fall and Spring', 'YR'),
    ('Full Year', 'YR'),
    ('', ''),
])
def test_normalize_term(raw, expected):
    assert normalize_term(raw) == expected


def test_pdf_and_excel_agree_on_year_long_rows():
    """The single most important normalization: 'FALL & SPRING' and 'YR' are the
    same term. Without this the same schedule imported two ways differs."""
    assert normalize_term('FALL & SPRING') == normalize_term('YR')


# ── row classification ──

@pytest.mark.parametrize('title,advisory,non_class', [
    ('Advisory Period', True, False),
    ('Homeroom', True, False),
    ('Vice Principal', False, True),
    ('Principal', False, True),
    ('Biology : The Living Earth CP [S1]', False, False),
    ('Culinary Arts CP [S2]', False, False),
    # A real course must not be mistaken for an administrator assignment.
    ('Intro to Counseling Careers', False, False),
    ('', False, False),
])
def test_classify_title(title, advisory, non_class):
    assert classify_title(title) == (advisory, non_class)


def test_excel_serial_to_date():
    # 46240 is the first day of school in the sample export.
    assert excel_serial_to_date(46240.0).isoformat() == '2026-08-06'
    assert excel_serial_to_date('46308').isoformat() == '2026-10-13'
    for junk in (None, '', 'abc', 0, -5, 10 ** 9):
        assert excel_serial_to_date(junk) is None


# ── Excel adapter ──

@needs_xls
def test_excel_reads_legacy_biff_xls():
    """openpyxl cannot open a legacy .xls at all; this must still work."""
    with open(SAMPLE_XLS, 'rb') as f:
        rows = parse_schedule_excel(f)
    assert len(rows) == 18


@needs_xls
def test_excel_extracts_every_field():
    with open(SAMPLE_XLS, 'rb') as f:
        rows = parse_schedule_excel(f)
    first = rows[0]
    assert first.period == 1
    assert first.term == 'Q1'
    assert first.course_number == '25248'
    assert first.course_title == 'Fashion Design CP [S1]'
    assert first.section_id == '1-019'
    assert first.teacher_name == 'Mar, J.'
    assert first.room == 'E114'
    assert first.school_year == '2026-2027'
    assert first.start_date.isoformat() == '2026-08-06'


@needs_xls
def test_excel_flags_advisory_and_non_class():
    with open(SAMPLE_XLS, 'rb') as f:
        rows = parse_schedule_excel(f)
    advisory = [r for r in rows if r.is_advisory]
    non_class = [r for r in rows if r.is_non_class]
    assert len(advisory) == 1
    assert advisory[0].period == 6
    # The section id carries the advisory's grade level — useful for grouping.
    assert '12th' in advisory[0].section_id
    assert len(non_class) == 1
    assert non_class[0].course_title == 'Vice Principal'
    assert non_class[0].period == 7


def test_excel_course_id_keeps_leading_zeros():
    """Advisory is course 0001; coercing it to a number would lose the zeros
    and stop it matching the catalog."""
    header = ['Course ID', 'Course Title', 'Term Code', 'Begin Period', 'Staff Name']
    rows = rows_to_parsed(header, [['0001', 'Advisory Period', 'YR', '6', 'Owens, E.']])
    assert rows[0].course_number == '0001'


def test_excel_rejects_a_file_missing_required_columns():
    with pytest.raises(ValueError) as e:
        rows_to_parsed(['Name', 'Nickname'], [['a', 'b']])
    assert 'Course ID' in str(e.value)


def test_read_tabular_detects_format_by_magic_bytes_not_extension():
    """Synergy names the file .XLS whatever is inside it."""
    csv_bytes = io.BytesIO(b'Course ID,Begin Period,Term Code\n0001,6,YR\n')
    csv_bytes.filename = 'actually_a_csv.XLS'
    header, rows = read_tabular(csv_bytes)
    assert header[0] == 'Course ID'
    assert rows == [['0001', '6', 'YR']]


# ── PDF adapter ──

@needs_pdf
def test_pdf_reads_all_rows_by_column_position():
    with open(SAMPLE_PDF, 'rb') as f:
        rows = parse_schedule_pdf(f)
    assert len(rows) == 18
    assert [r.period for r in rows[:4]] == [1, 1, 1, 1]
    assert [r.term for r in rows[:4]] == ['Q1', 'Q2', 'Q3', 'Q4']


@needs_pdf
def test_pdf_reassembles_wrapped_course_titles():
    """A long title wraps, leaving '[S1]' alone on the next baseline."""
    with open(SAMPLE_PDF, 'rb') as f:
        rows = parse_schedule_pdf(f)
    titles = [r.course_title for r in rows]
    assert 'World History, Culture & Geography CP [S1]' in titles
    assert 'World History, Culture & Geography CP [S2]' in titles


@needs_pdf
def test_pdf_excludes_footer_text_from_rows():
    """The legend block at the bottom sits in the same X band as course titles."""
    with open(SAMPLE_PDF, 'rb') as f:
        rows = parse_schedule_pdf(f)
    for r in rows:
        assert 'StudentVUE' not in r.course_title
        assert 'Please Note' not in r.course_title
        assert 'juhsd.net' not in r.course_title
        assert len(r.course_title) < 80


@needs_pdf
def test_pdf_normalizes_fall_and_spring_to_yr():
    with open(SAMPLE_PDF, 'rb') as f:
        rows = parse_schedule_pdf(f)
    year_long = [r for r in rows if r.term == 'YR']
    assert len(year_long) == 2                    # advisory + vice principal
    assert {r.period for r in year_long} == {6, 7}


@needs_pdf
def test_pdf_does_not_mistake_login_block_for_a_student_name():
    """The Login Information block shares text baselines with Student
    Information; reading the whole line yielded a student named 'stu.', which
    then failed to match silently instead of prompting for the student."""
    with open(SAMPLE_PDF, 'rb') as f:
        rows = parse_schedule_pdf(f)
    assert rows[0].student_name == ''
    assert rows[0].student_ref == ''
    # Header fields that ARE readable still come through.
    assert rows[0].school_year == '2026-2027'
    assert rows[0].grade_level == 11


# ── the two adapters must not drift apart ──

@needs_xls
@needs_pdf
def test_both_adapters_emit_the_same_shape():
    with open(SAMPLE_XLS, 'rb') as f:
        excel_rows = parse_schedule_file(f, 'x.xls')
    with open(SAMPLE_PDF, 'rb') as f:
        pdf_rows = parse_schedule_file(f, 'x.pdf')

    assert all(isinstance(r, ParsedRow) for r in excel_rows + pdf_rows)
    # Same fields populated, same value domains, from two very different files.
    for rows in (excel_rows, pdf_rows):
        assert {r.term for r in rows} <= {'Q1', 'Q2', 'Q3', 'Q4', 'YR'}
        assert all(isinstance(r.period, int) for r in rows)
        assert all(r.course_number for r in rows)
        assert all(r.school_year == '2026-2027' for r in rows)
    assert excel_rows[0].source == 'excel'
    assert pdf_rows[0].source == 'pdf'


# ── section IDs: what distinguishes two sections of the same course ──

@needs_xls
def test_excel_captures_a_section_id_on_every_row():
    """Section IDs are the only thing separating two sections of one course, and
    they differ per quarter in a 4x4 block (1-019 in Q1, 1-020 in Q2). Losing
    them silently would make the schedule un-editable at section granularity."""
    with open(SAMPLE_XLS, 'rb') as f:
        rows = parse_schedule_excel(f)
    blank = [r for r in rows if not r.section_id]
    assert not blank, f'{len(blank)} of {len(rows)} Excel rows lost their section ID'
    # Distinct per (period, term) — not one section reused across the year.
    assert len({r.section_id for r in rows}) > 1


@needs_pdf
def test_pdf_carries_no_section_id_because_the_printout_has_no_such_column():
    """Not a parser gap to be 'fixed'. The printed Synergy schedule has exactly
    six columns — Period, Course ID, Course Title, Teacher Name, Room, Semesters
    — and section is not among them. Anything filling this in from the PDF would
    be inventing data, so the importer leaves it empty and the preview says so.
    """
    with open(SAMPLE_PDF, 'rb') as f:
        rows = parse_schedule_pdf(f)
    assert rows, 'sample PDF should still parse'
    assert all(not r.section_id for r in rows)
    # Everything else the printout DOES carry must still arrive intact.
    assert all(r.course_number and r.course_title and r.term for r in rows)


@needs_xls
@needs_pdf
def test_the_excel_export_is_the_richer_source():
    """Stated plainly so the guidance in the import UI stays true: prefer Excel."""
    with open(SAMPLE_XLS, 'rb') as f:
        excel_rows = parse_schedule_excel(f)
    with open(SAMPLE_PDF, 'rb') as f:
        pdf_rows = parse_schedule_pdf(f)
    assert sum(1 for r in excel_rows if r.section_id) > sum(
        1 for r in pdf_rows if r.section_id)
