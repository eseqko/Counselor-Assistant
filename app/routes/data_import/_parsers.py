"""Shared file-parsing helpers for data import routes."""
import csv
import re
from flask import flash
from app.routes.data_import import HAS_OPENPYXL, SYNERGY_STATUS_MAP, load_workbook


def parse_upload_file(file):
    """Parse CSV or Excel file, return (header_row, data_rows).

    Returns (None, None) on error. header_row is a list of strings
    (the first row), data_rows is a list-of-lists for the remaining rows.

    Format is detected from the file's MAGIC BYTES, not its extension.
    Synergy exports legacy BIFF .xls, which openpyxl cannot open at all (it
    raises InvalidFileException telling you to use xlrd) — and it names the
    file .XLS regardless of what's inside. This previously accepted .xls by
    extension and then handed it to openpyxl, so every real Synergy .xls
    upload failed with an unhelpful error.
    """
    filename = (file.filename or '').lower()
    if not filename.endswith(('.csv', '.xlsx', '.xls', '.txt')):
        flash('Please upload a .csv, .xlsx or .xls file.', 'danger')
        return None, None

    try:
        from app.utils.schedule_parser import read_tabular
        header, rows = read_tabular(file)
    except ValueError as e:
        flash(str(e), 'danger')
        return None, None
    except Exception as e:
        flash(f'Could not read that file: {e}', 'danger')
        return None, None

    def as_text(v):
        if v is None:
            return ''
        if isinstance(v, float) and v.is_integer():
            return str(int(v))     # keep 5 as "5", not "5.0"
        return str(v)

    return [as_text(h) for h in header], [[as_text(c) for c in r] for r in rows]


# ── Grade import helpers ─────────────────────────────────────────

# Canonical header names → accepted header variations (case-insensitive)
GRADE_COL_ALIASES = {
    'school_year':  ('school year', 'schoolyear', 'year'),
    'perm_id':      ('perm id', 'permid', 'student id', 'student id #', 'student_id'),
    'grade_level':  ('grade level', 'gradelevel', 'grd', 'grade'),
    'grade':        ('letter grade', 'lettergrade', 'mark'),
    'mark_order':   ('mark order', 'markorder'),
    'mark_name':    ('mark name', 'markname', 'term'),
    'course_title': ('course title', 'coursetitle', 'course name', 'coursename'),
    'course_id':    ('course id', 'courseid', 'course number', 'coursenumber', 'course #', 'section id', 'sectionid'),
    'period':       ('period', 'per'),
    'audit_class':  ('audit class', 'auditclass', 'audit'),
    'staff_name':   ('staff name', 'staffname', 'teacher', 'teacher name'),
    'student_name': ('student name', 'studentname', 'name'),
    'credits_att':  ('credits att', 'credits attempted', 'cred att', 'credits'),
    'credits_comp': ('credits completed', 'cred comp', 'credits comp'),
    'gpa':          ('gpa',),
    'gender':       ('gender',),
}


_QUARTER_HEADER_RE = re.compile(r'^(?:quarter|qtr|q)\s*([1-4])$')


def find_quarter_columns(header):
    """[(column_index, quarter_number)] for every 'Quarter N' header, in order."""
    found = []
    for i, h in enumerate(header or []):
        m = _QUARTER_HEADER_RE.match(str(h or '').strip().lower())
        if m:
            found.append((i, int(m.group(1))))
    return found


def expand_quarter_columns(header, rows):
    """Unpivot a wide Synergy grade report (GRD401) into one row per grade.

    GRD401 ships a column PER QUARTER — Quarter 1 through Quarter 4 — with the
    letter grade sitting in whichever one matches that section's term, and the
    others blank. The rest of this importer expects the long shape: one row per
    student per course per quarter, with a single letter-grade column.

    Without this, a four-quarter export imported as a single quarter: the
    header scan below picks the FIRST "Quarter N" column it sees, so a full
    year of grades silently became Quarter 1 only — roughly a quarter of the
    file, with the rest dropped and no warning.

    Returns (header, rows) untouched when fewer than two quarter columns are
    present, so a single-quarter export keeps using the existing path.
    """
    qcols = find_quarter_columns(header)
    if len(qcols) < 2:
        return header, rows

    drop = {i for i, _ in qcols}
    keep = [i for i in range(len(header)) if i not in drop]
    new_header = [header[i] for i in keep] + ['Letter Grade', 'Mark Name']

    out = []
    for row in rows:
        base = [row[i] if i < len(row) else '' for i in keep]
        for ci, quarter in qcols:
            cell = row[ci] if ci < len(row) else None
            letter = '' if cell is None else str(cell).strip()
            if not letter:
                continue          # that quarter simply isn't graded for this row
            out.append(list(base) + [letter, 'Quarter %d' % quarter])
    return new_header, out


def build_grade_col_map(header):
    """Map canonical column names to 0-based indices from the actual header row.

    Handles Synergy grade report format where the letter grade column is named
    "Quarter 3" (or "Quarter 1", etc.) — the header itself encodes the quarter.
    """
    if not header:
        return {}
    col_map = {}
    header_lower = [h.strip().lower() for h in header]

    for canon, aliases in GRADE_COL_ALIASES.items():
        for alias in aliases:
            if alias in header_lower:
                col_map[canon] = header_lower.index(alias)
                break

    # ── Detect "Quarter X" column as the letter grade source ──
    # In Synergy grade reports, there's no separate "letter grade" or "mark name"
    # column. Instead, the header itself is "Quarter 3" and values are B, C-, etc.
    if 'grade' not in col_map:
        for i, h in enumerate(header_lower):
            m = re.match(r'(quarter|qtr|q)\s*(\d)', h)
            if m:
                col_map['grade'] = i
                col_map['_quarter_from_header'] = int(m.group(2))
                break

    # ── Disambiguate "Grade" column ──
    # If "grade" and "grade_level" both mapped to the same column (because the
    # header just says "Grade"), check if values look like grade levels (9-12)
    # or letter grades (A, B, C). Prefer treating standalone "Grade" next to
    # "Perm ID" as grade level when a Quarter column exists for letter grades.
    if 'grade' in col_map and 'grade_level' in col_map and col_map['grade'] == col_map['grade_level']:
        # Both matched the same column — resolve ambiguity
        if '_quarter_from_header' in col_map:
            # We found a Quarter column for letter grades, so "Grade" = grade level
            del col_map['grade']  # remove; letter grade comes from Quarter col
        else:
            # No Quarter column found; look for another "Grade" column
            for i, h in enumerate(header_lower):
                if h == 'grade' and i != col_map['grade_level']:
                    col_map['grade'] = i
                    break

    return col_map


def col(row, col_map, key):
    """Safely get a column value from a row by mapped key."""
    idx = col_map.get(key)
    if idx is None or idx >= len(row):
        return ''
    return str(row[idx]).strip()


def parse_quarter(mark_name_str):
    """Extract quarter number from mark name like 'Quarter 3' or 'Q3'."""
    s = str(mark_name_str or '').strip()
    if not s:
        return None
    # Try "Quarter 3", "Q3", "Qtr 3", or just "3"
    m = re.search(r'(?:quarter|qtr|q)\s*(\d)', s, re.IGNORECASE)
    if m:
        return int(m.group(1))
    # Try bare number
    try:
        val = int(s)
        if 1 <= val <= 4:
            return val
    except (ValueError, TypeError):
        pass
    return None


# ── ELPAC import helpers (Ellevation Education CSV format) ──────────

# Maps Ellevation CSV column headers (lowercase) to internal field names.
# Raw scores intentionally omitted — counselors only use scale + level.
ELPAC_HEADERS = {
    # identity
    'last name':                   'last_name',
    'middle name':                 'middle_name',
    'first name':                  'first_name',
    'student #':                   'perm_id',
    'test id #':                   'test_id',
    # student-level (same across all rows for one student)
    'el status':                   'el_status_in_file',
    'enrolled in us':              'us_school_entry_date',
    # test-level
    'test purpose':                'test_purpose',
    'test date':                   'test_date',
    'test grade level':            'test_grade_level',
    'test cluster':                'test_cluster',
    'test administrator':          'test_administrator',
    # domain scales + levels
    'listening scale score':       'listening_scale',
    'listening proficiency level': 'listening_level',
    'speaking scale score':        'speaking_scale',
    'speaking proficiency level':  'speaking_level',
    'reading scale score':         'reading_scale',
    'reading proficiency level':   'reading_level',
    'writing scale score':         'writing_scale',
    'writing proficiency level':   'writing_level',
    # composites
    'literacy scale score':        'literacy_scale',
    'literacy proficiency level':  'literacy_level',
    'oral scale score':            'oral_scale',
    'oral proficiency level':      'oral_level',
    'comprehension scale score':   'comprehension_scale',
    'comprehension proficiency level': 'comprehension_level',
    'composite/overall scale score':       'overall_scale',
    'composite/overall proficiency level': 'overall_level',
    'acpl scale score':            'acpl_scale',
    'acpl proficiency level':      'acpl_level',
}


def build_elpac_col_map(header_row):
    """Map canonical ELPAC field names to 0-based indices from header row."""
    if not header_row:
        return {}
    col_map = {}
    for i, h in enumerate(header_row):
        key = (h or '').strip().lower()
        if key in ELPAC_HEADERS:
            col_map[ELPAC_HEADERS[key]] = i
    return col_map


def is_synergy_format(header):
    """Detect if the header row matches a Synergy attendance export."""
    if not header:
        return False
    header_lower = [h.strip().lower() for h in header]
    # Synergy reports have "period 0", "period 1", … as column headers
    return 'period 0' in header_lower or ('period 1' in header_lower and 'perm id' in header_lower)


def convert_synergy_rows(header, rows):
    """Convert Synergy pivot-format rows into standard flat attendance rows.

    Synergy format: Student Name | Perm ID | Grd | Date | Period 0 | Period 1 | … | Period N | Relation cols…
    Output rows:    [student_id, date, period, status, course_name, reason]

    Student name/ID/grade may be blank on continuation rows — they carry
    forward from the most recent row that had them.
    """
    header_lower = [h.strip().lower() for h in header]

    # Find column indices
    period_cols = {}  # period_number -> column_index
    for idx, h in enumerate(header_lower):
        if h.startswith('period '):
            try:
                period_num = int(h.split(' ', 1)[1])
                period_cols[period_num] = idx
            except (ValueError, IndexError):
                pass

    # Find key columns by name
    def find_col(names):
        for name in names:
            if name in header_lower:
                return header_lower.index(name)
        return None

    id_col = find_col(['perm id', 'student id', 'student id #'])
    date_col = find_col(['date'])
    name_col = find_col(['student name', 'name'])
    grade_col = find_col(['grd', 'grade'])

    if id_col is None or date_col is None or not period_cols:
        return None  # Not a valid Synergy file

    flat_rows = []
    # Carry-forward state for grouped student rows
    current_id = ''
    current_name = ''

    for row in rows:
        # Pad short rows
        if len(row) < len(header):
            row.extend([''] * (len(header) - len(row)))

        # Carry forward student info when blank
        row_id = row[id_col].strip() if id_col is not None else ''
        row_name = row[name_col].strip() if name_col is not None else ''

        if row_id:
            current_id = row_id
            current_name = row_name
        elif not row_id and current_id:
            row_id = current_id
            row_name = current_name

        date_str = row[date_col].strip() if date_col is not None else ''

        if not row_id or not date_str:
            continue

        # Create one record per period column
        for period_num, col_idx in sorted(period_cols.items()):
            cell_value = row[col_idx].strip() if col_idx < len(row) else ''
            cell_lower = cell_value.lower()

            status, reason = SYNERGY_STATUS_MAP.get(
                cell_lower, ('absent', cell_value))

            flat_rows.append([
                row_id,       # student_id
                date_str,     # date
                str(period_num),  # period
                status,       # status (already lowercase)
                '',           # course_name
                reason,       # reason (original Synergy value)
            ])

    return flat_rows
