"""Student info bulk update: template download, upload."""
import io
from flask import render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
from app import db
from app.models.student import Student
from app.models.import_log import ImportLog
from app.utils.audit import log_action
from app.utils.helpers import parse_date
from app.routes.data_import import (
    data_import_bp, HAS_OPENPYXL, STUDENT_UPDATE_FIELDS,
    Workbook, Font, PatternFill, Alignment, Border, Side, get_column_letter,
)
from app.routes.data_import._parsers import parse_upload_file


@data_import_bp.route('/students/template')
@login_required
def student_update_template():
    """Download a pre-filled Excel template with current student data for bulk editing."""
    if not HAS_OPENPYXL:
        flash('Excel support requires openpyxl. Install it with: pip install openpyxl', 'danger')
        return redirect(url_for('data_import.index'))

    wb = Workbook()
    ws = wb.active
    ws.title = "Student Update"

    header_font = Font(name='Calibri', bold=True, color='FFFFFF', size=11)
    header_fill = PatternFill(start_color='2C5F8A', end_color='2C5F8A', fill_type='solid')
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin'))

    # Column order: Student ID (key), then all updatable fields
    columns = [
        ('Student ID #', 18),
        ('First Name', 16),
        ('Last Name', 16),
        ('Grade Level', 12),
        ('Gender', 14),
        ('Ethnicity', 16),
        ('Date of Birth', 14),
        ('Advisory', 14),
        ('Student Email', 26),
        ('Phone', 16),
        ('Parent/Guardian', 22),
        ('Parent Phone', 16),
        ('Parent Email', 26),
        ('Address', 30),
        ('EL Status', 14),
        ('EL Level', 10),
        ('IEP', 6),
        ('504', 6),
    ]

    # Map column header to db field name
    HEADER_TO_FIELD = {label: field for field, (label, _) in STUDENT_UPDATE_FIELDS.items()}
    HEADER_TO_FIELD['Student ID #'] = 'student_id_number'

    for col_idx, (name, width) in enumerate(columns, 1):
        cell = ws.cell(row=1, column=col_idx, value=name)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = thin_border
        cell.alignment = Alignment(horizontal='center')
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    # Pre-fill with current student data from caseload
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id
    ).filter(Student.status == 'active').order_by(Student.last_name, Student.first_name).all()

    for row_idx, s in enumerate(students, start=2):
        row_data = [
            s.student_id_number,
            s.first_name,
            s.last_name,
            s.grade_level,
            s.gender or '',
            s.ethnicity or '',
            s.date_of_birth.strftime('%m/%d/%Y') if s.date_of_birth else '',
            s.homeroom or '',
            s.email or '',
            s.phone or '',
            s.parent_guardian_name or '',
            s.parent_guardian_phone or '',
            s.parent_guardian_email or '',
            s.address or '',
            s.el_status or '',
            s.el_level or '',
            'Yes' if s.iep_status else '',
            'Yes' if s.section_504 else '',
        ]
        for col_idx, val in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.border = thin_border

    # Lock the Student ID column (light gray background to indicate read-only)
    lock_fill = PatternFill(start_color='F0F0F0', end_color='F0F0F0', fill_type='solid')
    for row_idx in range(2, len(students) + 2):
        ws.cell(row=row_idx, column=1).fill = lock_fill

    # Instructions sheet
    instr = wb.create_sheet('Instructions')
    instructions = [
        ('Student Info Bulk Update', ''),
        ('', ''),
        ('How it works', 'Edit any cells in the Student Update sheet, then upload the file. '
                         'Students are matched by Student ID #. Only changed fields are updated.'),
        ('Student ID #', 'DO NOT change this column — it is the key used to match students.'),
        ('Adding new columns', 'You can delete columns you do not need. '
                               'Only columns with recognized headers will be processed.'),
        ('Blank cells', 'Blank cells are skipped (existing value is kept). '
                        'To clear a field, enter a single dash (-).'),
        ('IEP / 504', 'Enter "Yes" to enable, "No" to disable, or leave blank to keep current value.'),
        ('EL Status', 'Valid values: EO, Newcomer, LTEL, RFEP'),
        ('Date of Birth', 'Format: MM/DD/YYYY or YYYY-MM-DD'),
        ('Grade Level', 'Enter the number only (e.g. 9, 10, 11, 12)'),
    ]
    for row_idx, (a, b) in enumerate(instructions, 1):
        instr.cell(row=row_idx, column=1, value=a).font = Font(
            name='Calibri', bold=bool(a), size=14 if row_idx == 1 else 11,
            color='2C5F8A' if row_idx == 1 else '000000')
        instr.cell(row=row_idx, column=2, value=b).font = Font(name='Calibri', size=11)
    instr.column_dimensions['A'].width = 20
    instr.column_dimensions['B'].width = 80

    ws.freeze_panes = 'A2'
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    log_action('export', 'student_update_template', details='Downloaded student update template')
    return send_file(buffer,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name='Student_Info_Update.xlsx')


@data_import_bp.route('/students/upload', methods=['GET', 'POST'])
@login_required
def student_update_upload():
    """Bulk update student profiles from an uploaded spreadsheet."""
    if request.method == 'POST':
        file = request.files.get('file')
        if not file:
            flash('Please select a file.', 'danger')
            return redirect(url_for('data_import.student_update_upload'))

        header, rows = parse_upload_file(file)
        if header is None:
            return redirect(url_for('data_import.student_update_upload'))

        # Build header → db field mapping from the uploaded column names
        header_lower = [h.strip().lower() for h in header]
        LABEL_TO_FIELD = {label.lower(): field for field, (label, _) in STUDENT_UPDATE_FIELDS.items()}
        LABEL_TO_FIELD['student id #'] = 'student_id_number'
        LABEL_TO_FIELD['student id'] = 'student_id_number'
        LABEL_TO_FIELD['perm id'] = 'student_id_number'
        LABEL_TO_FIELD['advisory'] = 'homeroom'
        LABEL_TO_FIELD['homeroom'] = 'homeroom'
        LABEL_TO_FIELD['dob'] = 'date_of_birth'

        col_map = {}  # col_index → field_name
        id_col = None
        for idx, h in enumerate(header_lower):
            field = LABEL_TO_FIELD.get(h)
            if field == 'student_id_number':
                id_col = idx
            elif field and field in STUDENT_UPDATE_FIELDS:
                col_map[idx] = field

        if id_col is None:
            flash('Could not find a Student ID column. Expected "Student ID #", "Student ID", or "Perm ID".', 'danger')
            return redirect(url_for('data_import.student_update_upload'))

        if not col_map:
            flash('No recognized data columns found. Check that your column headers match the template.', 'danger')
            return redirect(url_for('data_import.student_update_upload'))

        # Pre-load students on caseload
        student_cache = {}
        for s in Student.query.filter_by(assigned_counselor_id=current_user.id).all():
            student_cache[s.student_id_number] = s

        updated = 0
        skipped = 0
        not_found = 0
        field_changes = 0
        errors = []
        BATCH_SIZE = 200

        for row_idx, row in enumerate(rows, start=2):
            if len(row) <= id_col:
                continue
            sid = str(row[id_col]).strip()
            if not sid:
                continue

            student = student_cache.get(sid)
            if not student:
                not_found += 1
                continue

            changed = False
            for col_idx, field in col_map.items():
                if col_idx >= len(row):
                    continue
                raw = str(row[col_idx]).strip() if row[col_idx] else ''
                if not raw:
                    continue  # blank = keep existing

                # Clear field with dash
                if raw == '-':
                    if getattr(student, field):
                        setattr(student, field, '' if isinstance(getattr(student, field), str) else None)
                        changed = True
                        field_changes += 1
                    continue

                _, ftype = STUDENT_UPDATE_FIELDS[field]

                try:
                    if ftype == 'bool':
                        new_val = raw.lower() in ('yes', 'true', '1', 'y')
                        if raw.lower() in ('no', 'false', '0', 'n'):
                            new_val = False
                        elif raw.lower() not in ('yes', 'true', '1', 'y'):
                            continue  # unrecognized boolean, skip
                        if getattr(student, field) != new_val:
                            setattr(student, field, new_val)
                            changed = True
                            field_changes += 1
                    elif ftype == 'date':
                        new_date = parse_date(raw)
                        if new_date and getattr(student, field) != new_date:
                            setattr(student, field, new_date)
                            changed = True
                            field_changes += 1
                        elif not new_date:
                            errors.append(f'Row {row_idx}: Invalid date "{raw}" for {field}')
                    elif ftype == int:
                        new_val = int(float(raw))
                        if getattr(student, field) != new_val:
                            setattr(student, field, new_val)
                            changed = True
                            field_changes += 1
                    else:  # str
                        if getattr(student, field) != raw:
                            setattr(student, field, raw)
                            changed = True
                            field_changes += 1
                except (ValueError, TypeError) as e:
                    errors.append(f'Row {row_idx}: Bad value "{raw}" for {field}: {e}')
                    continue

            if changed:
                updated += 1
            else:
                skipped += 1

            if updated > 0 and updated % BATCH_SIZE == 0:
                db.session.commit()

        db.session.commit()
        log_action('import', 'student_update',
                   details=f'Bulk student update: {updated} students updated, '
                           f'{field_changes} fields changed, {skipped} unchanged')

        # Log the import
        db.session.add(ImportLog(
            user_id=current_user.id, import_type='student_update',
            records_added=0, records_updated=updated,
            records_skipped=skipped, errors_count=len(errors)))
        db.session.commit()

        if errors:
            flash(f'Updated {updated} students ({field_changes} fields changed), '
                  f'{skipped} unchanged, {not_found} not on caseload, {len(errors)} errors.', 'warning')
        else:
            msg = f'Updated {updated} students ({field_changes} fields changed).'
            if skipped:
                msg += f' {skipped} already up to date.'
            if not_found:
                msg += f' {not_found} student IDs not on your caseload.'
            flash(msg, 'success')

        return render_template('data_import/student_update_upload.html',
                               updated=updated, skipped=skipped, errors=errors)

    return render_template('data_import/student_update_upload.html',
                           updated=0, skipped=0, errors=None)
