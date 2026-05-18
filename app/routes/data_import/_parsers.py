"""Shared file-parsing helpers for data import routes."""
import csv
import re
from flask import flash
from app.routes.data_import import HAS_OPENPYXL, SYNERGY_STATUS_MAP, load_workbook


def parse_upload_file(file):
    """Parse CSV or Excel file, return (header_row, data_rows).

    Returns (None, None) on error. header_row is a list of strings
    (the first row), data_rows is a list-of-lists for the remaining rows.
    """
    filename = file.filename.lower()

    if filename.endswith('.csv'):
        try:
            text = file.read().decode('utf-8-sig')
            reader = csv.reader(text.splitlines())
            rows = list(reader)
            if rows:
                return rows[0], rows[1:]
            return [], []
        except Exception as e:
            flash(f'Could not read CSV: {str(e)}', 'danger')
            return None, None

    elif filename.endswith(('.xlsx', '.xls')):
        if not HAS_OPENPYXL:
            flash('Excel support requires openpyxl.', 'danger')
            return None, None
        try:
            wb = load_workbook(file, data_only=True)
            ws = wb.active
            header = []
            rows = []
            for idx, row in enumerate(ws.iter_rows(values_only=True)):
                str_row = [str(c) if c is not None else '' for c in row]
                if idx == 0:
                    header = str_row
                else:
                    rows.append(str_row)
            return header, rows
        except Exception as e:
            flash(f'Could not read Excel file: {str(e)}', 'danger')
            return None, None
    else:
        flash('Please upload a .csv or .xlsx file.', 'danger')
        return None, None


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
