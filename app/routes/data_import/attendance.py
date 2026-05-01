"""Attendance import: template download, upload, clear."""
import io
from flask import render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
from app import db
from app.models.student import Student
from app.models.attendance import AttendanceRecord
from app.models.import_log import ImportLog
from app.utils.audit import log_action
from app.utils.helpers import parse_date
from app.routes.data_import import (
    data_import_bp, HAS_OPENPYXL, VALID_ATTENDANCE,
    Workbook, Font, PatternFill, Alignment, Border, Side,
    get_column_letter, DataValidation,
)
from app.routes.data_import._parsers import (
    parse_upload_file, is_synergy_format, convert_synergy_rows,
)


@data_import_bp.route('/attendance/template')
@login_required
def attendance_template():
    """Download attendance import Excel template."""
    if not HAS_OPENPYXL:
        flash('Excel support requires openpyxl. Install with: pip install openpyxl', 'danger')
        return redirect(url_for('data_import.index'))

    wb = Workbook()
    ws = wb.active
    ws.title = "Attendance Import"

    header_font = Font(name='Calibri', bold=True, size=11, color='FFFFFF')
    header_fill = PatternFill(start_color='2C5F8A', end_color='2C5F8A', fill_type='solid')
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin'),
    )

    columns = [
        ('Student ID #', 16),
        ('Date', 14),
        ('Period', 8),
        ('Status', 14),
        ('Course Name', 30),
        ('Reason', 30),
    ]

    for col_idx, (name, width) in enumerate(columns, 1):
        cell = ws.cell(row=1, column=col_idx, value=name)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = thin_border
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    # Data validation for Status
    status_dv = DataValidation(
        type='list', formula1='"Present,Absent,Tardy,Excused"', allow_blank=False,
        showErrorMessage=True, errorTitle='Invalid Status',
        error='Choose: Present, Absent, Tardy, or Excused'
    )
    status_dv.sqref = 'D2:D5000'
    ws.add_data_validation(status_dv)

    # Period validation (0-10 to support Synergy periods)
    period_dv = DataValidation(
        type='list', formula1='"0,1,2,3,4,5,6,7,8,9,10"', allow_blank=True,
        showErrorMessage=True, errorTitle='Invalid Period',
        error='Enter period 0-10'
    )
    period_dv.sqref = 'C2:C5000'
    ws.add_data_validation(period_dv)

    # Instructions sheet
    instr = wb.create_sheet('Instructions')
    instr.sheet_properties.tabColor = 'E8A838'
    instructions = [
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
    ]
    for row_idx, (a, b) in enumerate(instructions, 1):
        instr.cell(row=row_idx, column=1, value=a).font = Font(
            name='Calibri', bold=bool(a), size=14 if row_idx == 1 else 11,
            color='2C5F8A' if row_idx == 1 else '000000')
        instr.cell(row=row_idx, column=2, value=b).font = Font(name='Calibri', size=11)
    instr.column_dimensions['A'].width = 18
    instr.column_dimensions['B'].width = 75

    ws.freeze_panes = 'A2'
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    log_action('export', 'attendance_template', details='Downloaded attendance template')
    return send_file(buffer,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name='Attendance_Import_Template.xlsx')


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
        errors = []

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

            student = Student.query.filter_by(
                student_id_number=str(student_id_str).strip()).first()
            if not student:
                # For Synergy whole-school reports, silently skip non-caseload students
                if is_synergy:
                    not_on_caseload += 1
                    continue
                errors.append(f'Row {row_idx}: Student ID {student_id_str} not found')
                continue

            # Skip duplicates (check in-memory set instead of DB query)
            att_key = (student.id, att_date, period_val)
            if att_key in existing_keys:
                skipped += 1
                continue
            existing_keys.add(att_key)  # Track newly added records too

            record = AttendanceRecord(
                student_id=student.id,
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
                           + (f', {not_on_caseload} not on caseload' if not_on_caseload else ''))

        # Log the import
        db.session.add(ImportLog(
            user_id=current_user.id, import_type='attendance',
            records_added=added, records_skipped=skipped, errors_count=len(errors)))
        db.session.commit()

        if is_synergy:
            fmt_msg = f'Synergy import: {added} records added, {skipped} duplicates skipped.'
            if not_on_caseload:
                fmt_msg += f' {not_on_caseload} records skipped (students not on your caseload).'
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
    student_ids = [row[0] for row in Student.query.filter_by(
        assigned_counselor_id=current_user.id).with_entities(Student.id).all()]
    count = AttendanceRecord.query.filter(
        AttendanceRecord.student_id.in_(student_ids)).delete(synchronize_session=False)
    db.session.commit()
    log_action('delete', 'attendance', details=f'Cleared {count} attendance records')
    flash(f'Cleared {count} attendance records.', 'warning')
    return redirect(url_for('data_import.index'))
