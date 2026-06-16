"""Attendance import: template download, upload, clear."""
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models.student import Student
from app.models.attendance import AttendanceRecord
from app.models.import_log import ImportLog
from app.utils.audit import log_action
from app.utils.helpers import parse_date
from app.utils.excel_helpers import build_import_workbook, workbook_response
from app.utils.caseload import caseload_student_ids
from app.routes.data_import import (
    data_import_bp, HAS_OPENPYXL, VALID_ATTENDANCE,
    Workbook, Font, PatternFill, Alignment, Border, Side,
    get_column_letter, DataValidation,
)
from app.routes.data_import._parsers import (
    parse_upload_file, is_synergy_format, convert_synergy_rows,
)


_OPENPYXL_KIT = {
    'Workbook': Workbook, 'Font': Font, 'PatternFill': PatternFill,
    'Alignment': Alignment, 'Border': Border, 'Side': Side,
    'get_column_letter': get_column_letter, 'DataValidation': DataValidation,
}


@data_import_bp.route('/attendance/template')
@login_required
def attendance_template():
    """Download attendance import Excel template."""
    if not HAS_OPENPYXL:
        flash('Excel support requires openpyxl. Install with: pip install openpyxl', 'danger')
        return redirect(url_for('data_import.index'))

    wb = build_import_workbook(
        _OPENPYXL_KIT,
        sheet_title='Attendance Import',
        columns=[
            ('Student ID #', 16),
            ('Date', 14),
            ('Period', 8),
            ('Status', 14),
            ('Course Name', 30),
            ('Reason', 30),
        ],
        validations=[
            {'formula1': '"Present,Absent,Tardy,Excused"', 'sqref': 'D2:D5000',
             'allow_blank': False,
             'error_title': 'Invalid Status',
             'error_message': 'Choose: Present, Absent, Tardy, or Excused'},
            {'formula1': '"0,1,2,3,4,5,6,7,8,9,10"', 'sqref': 'C2:C5000',
             'allow_blank': True,
             'error_title': 'Invalid Period',
             'error_message': 'Enter period 0-10'},
        ],
        instructions=[
            ('ATTENDANCE IMPORT TEMPLATE', ''),
            ('', ''),
            ('Column', 'Instructions'),
            ('Student ID #', 'Required. Must match a student in your caseload.'),
            ('Date', 'Required. Format: MM/DD/YYYY or YYYY-MM-DD'),
            ('Period', 'Optional. Class period 0-10. (1-4 core, 5 extracurricular, 6 advisory)'),
            ('Status', 'Required. Present, Absent, Tardy, or Excused.'),
            ('Course Name', 'Optional. Name of the class.'),
            ('Reason', 'Optional. Reason for absence/tardy.'),
            ('', ''),
            ('TIPS:', ''),
            ('', 'You can paste data exported from your SIS (Synergy, Aeries, PowerSchool, etc.)'),
            ('', 'One row per student per period. Daily attendance = one row per student.'),
            ('', 'Duplicate rows (same student+date+period) will be skipped.'),
        ],
    )

    log_action('export', 'attendance_template', details='Downloaded attendance template')
    return workbook_response(wb, 'Attendance_Import_Template.xlsx')


@data_import_bp.route('/attendance/upload', methods=['GET', 'POST'])
@login_required
def attendance_upload():
    """Upload attendance data from Excel or CSV."""
    if request.method == 'POST':
        file = request.files.get('file')
        if not file:
            flash('Please select a file.', 'danger')
            return redirect(url_for('data_import.attendance_upload'))

        header, rows = parse_upload_file(file)
        if header is None:
            return redirect(url_for('data_import.attendance_upload'))

        # Auto-detect Synergy format and convert to standard rows
        is_synergy = is_synergy_format(header)
        if is_synergy:
            rows = convert_synergy_rows(header, rows)
            if rows is None:
                flash('Could not parse Synergy file. Check that it has Perm ID, Date, and Period columns.', 'danger')
                return redirect(url_for('data_import.attendance_upload'))

        added = 0
        skipped = 0
        not_on_caseload = 0
        shadow_added = 0  # students created for school-wide comparison data
        errors = []

        # Pre-load student lookup once: student_id_number → db id
        student_cache = {
            s.student_id_number: s.id
            for s in Student.query.with_entities(
                Student.student_id_number, Student.id).all()
        }

        # Pre-load existing attendance keys to avoid per-row duplicate checks
        caseload_ids = list(student_cache.values())
        existing_keys = set()
        if caseload_ids:
            for sid, att_date, period in db.session.query(
                AttendanceRecord.student_id, AttendanceRecord.date, AttendanceRecord.period
            ).filter(AttendanceRecord.student_id.in_(caseload_ids)).all():
                existing_keys.add((sid, att_date, period))

        for row_idx, row in enumerate(rows, start=2):
            if len(row) < 4:
                row.extend([''] * (6 - len(row)))
            student_id_str, date_str, period_str, status_str = row[0], row[1], row[2], row[3]
            course_name = row[4] if len(row) > 4 else ''
            reason = row[5] if len(row) > 5 else ''

            if not student_id_str and not date_str and not status_str:
                continue

            row_errors = []
            if not student_id_str:
                row_errors.append('Student ID # required')
            if not date_str:
                row_errors.append('Date required')
            if not status_str:
                row_errors.append('Status required')

            # Synergy rows already have clean status; template rows need validation
            status_clean = str(status_str or '').strip().lower()
            if status_clean and status_clean not in VALID_ATTENDANCE:
                row_errors.append(f'Invalid status: {status_str}')

            att_date = parse_date(str(date_str).strip()) if date_str else None
            if date_str and not att_date:
                row_errors.append(f'Invalid date: {date_str}')

            period_val = None
            if period_str:
                try:
                    period_val = int(float(period_str))
                    if period_val < 0 or period_val > 10:
                        row_errors.append(f'Period must be 0-10, got {period_val}')
                except (ValueError, TypeError):
                    row_errors.append(f'Invalid period: {period_str}')

            if row_errors:
                if not is_synergy:
                    errors.append(f'Row {row_idx}: ' + '; '.join(row_errors))
                continue

            sid_clean = str(student_id_str).strip()
            student_db_id = student_cache.get(sid_clean)
            if not student_db_id:
                # School-wide comparison data: auto-create a shadow Student for
                # Synergy whole-school exports so attendance is retained for the
                # "vs school" reports. Shadow students are invisible to all
                # caseload UI (assigned_counselor_id=None + is_shadow=True).
                if is_synergy and sid_clean:
                    shadow = Student(
                        student_id_number=sid_clean,
                        first_name='Unknown',
                        last_name='Student',
                        assigned_counselor_id=None,
                        status='active',
                        is_shadow=True,
                    )
                    db.session.add(shadow)
                    db.session.flush()
                    student_db_id = shadow.id
                    student_cache[sid_clean] = shadow.id
                    shadow_added += 1
                elif is_synergy:
                    not_on_caseload += 1
                    continue
                else:
                    errors.append(f'Row {row_idx}: Student ID {student_id_str} not found')
                    continue

            # Skip duplicates (check in-memory set instead of DB query)
            att_key = (student_db_id, att_date, period_val)
            if att_key in existing_keys:
                skipped += 1
                continue
            existing_keys.add(att_key)  # Track newly added records too

            record = AttendanceRecord(
                student_id=student_db_id,
                date=att_date,
                period=period_val,
                status=status_clean,
                course_name=str(course_name or '').strip(),
                reason=str(reason or '').strip(),
                imported_by_id=current_user.id,
            )
            db.session.add(record)
            added += 1

        db.session.commit()
        log_action('import', 'attendance',
                   details=f'Imported attendance: {added} added, {skipped} skipped'
                           + (f', {shadow_added} school-wide added' if shadow_added else '')
                           + (f', {not_on_caseload} unidentifiable' if not_on_caseload else ''))

        # Log the import
        db.session.add(ImportLog(
            user_id=current_user.id, import_type='attendance',
            records_added=added, records_skipped=skipped, errors_count=len(errors)))
        db.session.commit()

        if is_synergy:
            fmt_msg = f'Synergy import: {added} records added, {skipped} duplicates skipped.'
            if shadow_added:
                fmt_msg += f' {shadow_added} additional records kept for school-wide comparison reports (students not on your caseload).'
            if not_on_caseload:
                fmt_msg += f' {not_on_caseload} rows skipped (no student ID).'
            if errors:
                fmt_msg += f' {len(errors)} errors.'
                flash(fmt_msg, 'warning')
            else:
                flash(fmt_msg, 'success')
        else:
            if errors:
                flash(f'Imported with issues: {added} added, {skipped} duplicates skipped, {len(errors)} errors.', 'warning')
            else:
                flash(f'Attendance imported: {added} records added, {skipped} duplicates skipped.', 'success')

        return render_template('data_import/attendance_upload.html',
                               added=added, skipped=skipped, errors=errors)

    return render_template('data_import/attendance_upload.html',
                           added=0, skipped=0, errors=None)


@data_import_bp.route('/attendance/clear', methods=['POST'])
@login_required
def clear_attendance():
    """Clear all attendance records for current counselor's students."""
    student_ids = caseload_student_ids(current_user)
    count = AttendanceRecord.query.filter(
        AttendanceRecord.student_id.in_(student_ids)).delete(synchronize_session=False)
    db.session.commit()
    log_action('delete', 'attendance', details=f'Cleared {count} attendance records')
    flash(f'Cleared {count} attendance records.', 'warning')
    return redirect(url_for('data_import.index'))
