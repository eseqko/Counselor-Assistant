"""ELPAC import: Ellevation Education CSV exports, accepted as-is.

The Ellevation export has 41 columns including 4 domains, 3 composites,
Overall, and ACPL. We match Student # → caseload, fall back to (Last, First)
name match. Only adds records for students currently in the caseload —
graduates, withdrawals, and other counselors' students are silently skipped.
"""
import csv
import io
from datetime import datetime, date
from flask import render_template, request, redirect, url_for, flash, jsonify, Response
from flask_login import login_required, current_user
from app import db, csrf
from app.models.student import Student
from app.models.elpac import ELPACScore
from app.models.import_log import ImportLog
from app.utils.audit import log_action
from app.utils.caseload import caseload_student_ids
from app.routes.data_import import data_import_bp
from app.routes.data_import._parsers import (
    parse_upload_file, build_elpac_col_map, ELPAC_HEADERS,
)


# ── Helpers ─────────────────────────────────────────────────────────


def _col(row, col_map, key):
    """Get a column value by canonical key. Returns '' if missing."""
    idx = col_map.get(key)
    if idx is None or idx >= len(row):
        return ''
    return str(row[idx]).strip()


def _parse_int(val):
    if val is None or str(val).strip() == '':
        return None
    try:
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return None


def _parse_date(val):
    if not val:
        return None
    val = str(val).strip()
    for fmt in ('%m/%d/%Y', '%Y-%m-%d', '%m/%d/%y'):
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            continue
    return None


def _derive_school_year(d):
    if not d:
        return None
    return f"{d.year}-{d.year + 1}" if d.month >= 7 else f"{d.year - 1}-{d.year}"


def _build_lookups():
    """Return (id_to_student_id, name_to_student_id) for fast matching."""
    students = Student.query.with_entities(
        Student.id, Student.student_id_number, Student.last_name, Student.first_name).all()
    by_id = {s.student_id_number: s.id for s in students if s.student_id_number}
    by_name = {}
    for s in students:
        key = f"{s.last_name.strip().lower()}, {s.first_name.strip().lower()}"
        by_name[key] = s.id
    return by_id, by_name


# Canonical Ellevation header row (used when downloading the empty template)
ELLEVATION_TEMPLATE_HEADER = [
    'Last Name', 'Middle Name', 'First Name', 'School Name', 'School LEA Code',
    'Test ID #', 'Student #', 'EL Status', 'Enrolled in US', 'Test Type',
    'Test Date', 'Test Grade Level', 'Test Cluster', 'Test Purpose', 'Test Administrator',
    'Listening Raw Score', 'Listening Scale Score', 'Listening Proficiency Level',
    'Speaking Raw Score', 'Speaking Scale Score', 'Speaking Proficiency Level',
    'Reading Raw Score', 'Reading Scale Score', 'Reading Proficiency Level',
    'Writing Raw Score', 'Writing Scale Score', 'Writing Proficiency Level',
    'Literacy Raw Score', 'Literacy Scale Score', 'Literacy Proficiency Level',
    'Oral Raw Score', 'Oral Scale Score', 'Oral Proficiency Level',
    'Comprehension Raw Score', 'Comprehension Scale Score', 'Comprehension Proficiency Level',
    'Composite/Overall Raw Score', 'Composite/Overall Scale Score', 'Composite/Overall Proficiency Level',
    'ACPL Raw Score', 'ACPL Scale Score', 'ACPL Proficiency Level',
]


# ── Routes ──────────────────────────────────────────────────────────


@data_import_bp.route('/elpac/template')
@login_required
def elpac_template():
    """Download the empty Ellevation-format CSV template."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(ELLEVATION_TEMPLATE_HEADER)
    log_action('export', 'elpac_template', details='Downloaded ELPAC template')
    return Response(
        buf.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=ELPAC_Ellevation_Template.csv'},
    )


@data_import_bp.route('/elpac/preview', methods=['POST'])
@csrf.exempt
@login_required
def elpac_preview():
    """AJAX endpoint: parse uploaded file, report match counts + sample rows."""
    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'No file provided'}), 400

    header, rows = parse_upload_file(file)
    if header is None:
        return jsonify({'error': 'Could not read file'}), 400

    col_map = build_elpac_col_map(header)
    if 'perm_id' not in col_map and 'last_name' not in col_map:
        return jsonify({
            'error': "File doesn't look like an Ellevation ELPAC export. "
                     "Expected 'Student #' or 'Last Name' column."
        }), 400

    detected = [k for k in col_map.keys() if not k.startswith('_')]

    caseload = set(caseload_student_ids(current_user))
    by_id, by_name = _build_lookups()

    total = 0
    on_caseload = 0
    other_students = 0
    no_match = 0
    sample = []

    for row in rows:
        while len(row) < len(header):
            row.append('')
        perm_id = _col(row, col_map, 'perm_id')
        last_name = _col(row, col_map, 'last_name')
        first_name = _col(row, col_map, 'first_name')
        test_date = _col(row, col_map, 'test_date')
        if not (perm_id or last_name) or not test_date:
            continue
        total += 1

        student_db_id = by_id.get(perm_id) if perm_id else None
        if not student_db_id and last_name and first_name:
            key = f"{last_name.lower()}, {first_name.lower()}"
            student_db_id = by_name.get(key)

        if student_db_id is None:
            no_match += 1
        elif student_db_id in caseload:
            on_caseload += 1
        else:
            other_students += 1

        if len(sample) < 5:
            name_display = f"{last_name}, {first_name}" if last_name else f"ID {perm_id}"
            sample.append({
                'student': name_display,
                'perm_id': perm_id,
                'test_date': test_date,
                'test_purpose': _col(row, col_map, 'test_purpose'),
                'overall_level': _col(row, col_map, 'overall_level'),
                'matched_caseload': student_db_id in caseload if student_db_id else False,
            })

    return jsonify({
        'detected_columns': detected,
        'total_rows': total,
        'on_caseload': on_caseload,
        'other_students': other_students,
        'no_match': no_match,
        'sample': sample,
    })


@data_import_bp.route('/elpac/upload', methods=['GET', 'POST'])
@login_required
def elpac_upload():
    """Upload ELPAC test results from Ellevation CSV/Excel."""
    if request.method != 'POST':
        return render_template('data_import/elpac_upload.html',
                               added=0, updated=0, errors=None)

    file = request.files.get('file')
    if not file:
        flash('Please select a file.', 'danger')
        return redirect(url_for('data_import.elpac_upload'))

    header, rows = parse_upload_file(file)
    if header is None:
        return redirect(url_for('data_import.elpac_upload'))

    col_map = build_elpac_col_map(header)
    if 'perm_id' not in col_map and 'last_name' not in col_map:
        flash("File doesn't look like an Ellevation ELPAC export. "
              "Expected 'Student #' or 'Last Name' columns.", 'danger')
        return redirect(url_for('data_import.elpac_upload'))

    caseload_set = set(caseload_student_ids(current_user))
    by_id, by_name = _build_lookups()

    added = 0
    updated = 0
    not_on_caseload = 0
    no_match = 0
    errors = []
    us_entry_updates = 0
    BATCH = 200

    for row_idx, row in enumerate(rows, start=2):
        while len(row) < len(header):
            row.append('')

        perm_id = _col(row, col_map, 'perm_id')
        last_name = _col(row, col_map, 'last_name')
        first_name = _col(row, col_map, 'first_name')
        test_date_raw = _col(row, col_map, 'test_date')
        purpose = _col(row, col_map, 'test_purpose') or 'Summative'

        # Skip blank rows
        if not (perm_id or last_name) and not test_date_raw:
            continue

        test_date = _parse_date(test_date_raw)
        if not test_date:
            errors.append(f"Row {row_idx}: missing/invalid Test Date")
            continue

        # Resolve student
        student_db_id = by_id.get(perm_id) if perm_id else None
        if not student_db_id and last_name and first_name:
            student_db_id = by_name.get(f"{last_name.lower()}, {first_name.lower()}")

        if student_db_id is None:
            no_match += 1
            continue
        if student_db_id not in caseload_set:
            not_on_caseload += 1
            continue

        # Populate us_school_entry_date on student if currently NULL
        us_entry_raw = _col(row, col_map, 'us_school_entry_date')
        if us_entry_raw:
            us_entry = _parse_date(us_entry_raw)
            if us_entry:
                student = Student.query.get(student_db_id)
                if student and not student.us_school_entry_date:
                    student.us_school_entry_date = us_entry
                    us_entry_updates += 1

        # Upsert
        existing = ELPACScore.query.filter_by(
            student_id=student_db_id,
            test_date=test_date,
            test_purpose=purpose,
        ).first()

        score = existing or ELPACScore(
            student_id=student_db_id,
            imported_by_id=current_user.id,
        )
        score.test_purpose = purpose
        score.test_date = test_date
        score.school_year = _derive_school_year(test_date)
        score.test_id = _col(row, col_map, 'test_id') or score.test_id
        score.test_grade_level = _parse_int(_col(row, col_map, 'test_grade_level'))
        score.test_cluster = _col(row, col_map, 'test_cluster') or None
        score.test_administrator = _col(row, col_map, 'test_administrator') or None

        for prefix in ('listening', 'speaking', 'reading', 'writing',
                       'literacy', 'oral', 'comprehension', 'overall', 'acpl'):
            setattr(score, f'{prefix}_scale',
                    _parse_int(_col(row, col_map, f'{prefix}_scale')))
            setattr(score, f'{prefix}_level',
                    _parse_int(_col(row, col_map, f'{prefix}_level')))

        if existing:
            updated += 1
        else:
            db.session.add(score)
            added += 1

        if (added + updated) % BATCH == 0:
            db.session.commit()

    db.session.commit()

    db.session.add(ImportLog(
        user_id=current_user.id,
        import_type='elpac',
        records_added=added,
        records_updated=updated,
        records_skipped=not_on_caseload + no_match,
        errors_count=len(errors),
    ))
    db.session.commit()

    log_action('import', 'elpac',
               details=f'ELPAC import: {added} added, {updated} updated, '
                       f'{not_on_caseload} not on caseload, {no_match} no match')

    summary = (
        f"ELPAC import complete: {added} added, {updated} updated."
        + (f" {not_on_caseload} skipped (not on your caseload — graduates, "
           f"withdrawals, or other counselors' students)." if not_on_caseload else '')
        + (f" {no_match} students not found in your roster." if no_match else '')
        + (f" {us_entry_updates} students had US school entry date populated." if us_entry_updates else '')
    )
    flash(summary, 'success' if added or updated else 'warning')

    return render_template('data_import/elpac_upload.html',
                           added=added, updated=updated, errors=errors)


@data_import_bp.route('/elpac/clear', methods=['POST'])
@login_required
def clear_elpac():
    """Delete all ELPAC records for the current counselor's caseload."""
    student_ids = caseload_student_ids(current_user)
    count = ELPACScore.query.filter(
        ELPACScore.student_id.in_(student_ids)).delete(synchronize_session=False)
    db.session.commit()
    log_action('delete', 'elpac', details=f'Cleared {count} ELPAC records')
    flash(f'Cleared {count} ELPAC records.', 'warning')
    return redirect(url_for('data_import.index'))
