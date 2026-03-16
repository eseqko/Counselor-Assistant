import io
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
from app import db
from app.models.student import Student, Tag
from app.utils.audit import log_action
from app.utils.helpers import parse_date
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, Protection
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

caseload_bp = Blueprint('caseload', __name__)

# ---------- EL status constants ----------
VALID_EL_STATUSES = {'Newcomer', 'LTEL', 'RFEP', 'EO', ''}
VALID_EL_LEVELS = {'EL 1', 'EL 2', 'EL 3', ''}


@caseload_bp.route('/')
@login_required
def index():
    search = request.args.get('search', '').strip()
    grade = request.args.get('grade', '')
    status = request.args.get('status', 'active')
    tag_filter = request.args.get('tag', '')
    el_filter = request.args.get('el_status', '')

    query = Student.query.filter_by(assigned_counselor_id=current_user.id)

    if status:
        query = query.filter_by(status=status)
    if grade:
        query = query.filter_by(grade_level=int(grade))
    if search:
        query = query.filter(
            db.or_(
                Student.first_name.ilike(f'%{search}%'),
                Student.last_name.ilike(f'%{search}%'),
                Student.student_id_number.ilike(f'%{search}%'),
            )
        )
    if tag_filter:
        query = query.filter(Student.tags.any(Tag.name == tag_filter))
    if el_filter:
        query = query.filter_by(el_status=el_filter)

    students = query.order_by(Student.last_name, Student.first_name).all()
    tags = Tag.query.order_by(Tag.name).all()

    return render_template('caseload/index.html',
        students=students, search=search, grade=grade,
        status=status, tag_filter=tag_filter, el_filter=el_filter, tags=tags)


@caseload_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_student():
    if request.method == 'POST':
        el_status = request.form.get('el_status', 'EO')
        el_level = request.form.get('el_level', '') if el_status == 'Newcomer' else ''

        student = Student(
            student_id_number=request.form['student_id_number'],
            first_name=request.form['first_name'],
            last_name=request.form['last_name'],
            grade_level=int(request.form['grade_level']) if request.form.get('grade_level') else None,
            date_of_birth=parse_date(request.form.get('date_of_birth')),
            gender=request.form.get('gender', ''),
            ethnicity=request.form.get('ethnicity', ''),
            email=request.form.get('email', ''),
            phone=request.form.get('phone', ''),
            parent_guardian_name=request.form.get('parent_guardian_name', ''),
            parent_guardian_phone=request.form.get('parent_guardian_phone', ''),
            parent_guardian_email=request.form.get('parent_guardian_email', ''),
            address=request.form.get('address', ''),
            homeroom=request.form.get('homeroom', ''),
            assigned_counselor_id=current_user.id,
            iep_status='iep_status' in request.form,
            section_504='section_504' in request.form,
            el_status=el_status,
            el_level=el_level,
            ell_status=(el_status in ('Newcomer', 'LTEL', 'RFEP')),
            enrollment_date=parse_date(request.form.get('enrollment_date')),
        )
        # Handle tags
        tag_names = request.form.get('tags', '').split(',')
        for name in tag_names:
            name = name.strip()
            if name:
                tag = Tag.query.filter_by(name=name).first()
                if not tag:
                    tag = Tag(name=name)
                    db.session.add(tag)
                student.tags.append(tag)

        db.session.add(student)
        db.session.commit()
        log_action('create', 'student', student.id, f'Added student {student.full_name}')
        flash(f'Student {student.full_name} added successfully.', 'success')
        return redirect(url_for('caseload.view_student', id=student.id))

    tags = Tag.query.order_by(Tag.name).all()
    return render_template('caseload/add.html', tags=tags,
        el_statuses=Student.EL_STATUSES, el_levels=Student.EL_LEVELS)


@caseload_bp.route('/<int:id>')
@login_required
def view_student(id):
    student = Student.query.get_or_404(id)
    log_action('view', 'student', student.id)
    notes = student.notes.limit(10).all()
    services = student.service_records.limit(10).all()
    return render_template('caseload/view.html',
        student=student, notes=notes, services=services)


@caseload_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_student(id):
    student = Student.query.get_or_404(id)

    if request.method == 'POST':
        student.student_id_number = request.form['student_id_number']
        student.first_name = request.form['first_name']
        student.last_name = request.form['last_name']
        student.grade_level = int(request.form['grade_level']) if request.form.get('grade_level') else None
        student.date_of_birth = parse_date(request.form.get('date_of_birth'))
        student.gender = request.form.get('gender', '')
        student.ethnicity = request.form.get('ethnicity', '')
        student.email = request.form.get('email', '')
        student.phone = request.form.get('phone', '')
        student.parent_guardian_name = request.form.get('parent_guardian_name', '')
        student.parent_guardian_phone = request.form.get('parent_guardian_phone', '')
        student.parent_guardian_email = request.form.get('parent_guardian_email', '')
        student.address = request.form.get('address', '')
        student.homeroom = request.form.get('homeroom', '')
        student.status = request.form.get('status', 'active')
        student.iep_status = 'iep_status' in request.form
        student.section_504 = 'section_504' in request.form
        student.el_status = request.form.get('el_status', 'EO')
        student.el_level = request.form.get('el_level', '') if student.el_status == 'Newcomer' else ''
        student.ell_status = (student.el_status in ('Newcomer', 'LTEL', 'RFEP'))

        db.session.commit()
        log_action('update', 'student', student.id, f'Updated student {student.full_name}')
        flash(f'Student {student.full_name} updated.', 'success')
        return redirect(url_for('caseload.view_student', id=student.id))

    tags = Tag.query.order_by(Tag.name).all()
    return render_template('caseload/edit.html', student=student, tags=tags,
        el_statuses=Student.EL_STATUSES, el_levels=Student.EL_LEVELS)


@caseload_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete_student(id):
    student = Student.query.get_or_404(id)
    name = student.full_name
    log_action('delete', 'student', student.id, f'Deleted student {name}')
    db.session.delete(student)
    db.session.commit()
    flash(f'Student {name} removed from caseload.', 'warning')
    return redirect(url_for('caseload.index'))


# =====================================================================
#  EXCEL TEMPLATE DOWNLOAD
# =====================================================================

@caseload_bp.route('/download-template')
@login_required
def download_template():
    """Generate and download a formatted Excel template for caseload upload."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Caseload Import"

    # --- Styles ---
    header_font = Font(name='Calibri', bold=True, size=11, color='FFFFFF')
    header_fill = PatternFill(start_color='2C5F8A', end_color='2C5F8A', fill_type='solid')
    header_align = Alignment(horizontal='center', vertical='center', wrap_text=True)
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin'),
    )
    locked = Protection(locked=True)
    unlocked = Protection(locked=False)

    # --- Column definitions ---
    columns = [
        ('First Name', 20, 'Enter student first name'),
        ('Last Name', 20, 'Enter student last name'),
        ('Grade', 8, 'Grade level (6-12)'),
        ('Student ID #', 16, 'Unique school student ID'),
        ('Email', 30, 'Student email address'),
        ('EL Status', 16, 'Newcomer, LTEL, RFEP, or EO'),
        ('EL Level', 12, 'Only if Newcomer: EL 1, EL 2, or EL 3'),
        ('IEP', 8, 'Yes or leave blank'),
        ('504 Plan', 10, 'Yes or leave blank'),
    ]

    # --- Write headers ---
    for col_idx, (name, width, _) in enumerate(columns, 1):
        cell = ws.cell(row=1, column=col_idx, value=name)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = thin_border
        cell.protection = locked
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    # --- Data validation ---
    # Grade: 6-12
    grade_dv = DataValidation(
        type='list', formula1='"6,7,8,9,10,11,12"', allow_blank=True,
        showErrorMessage=True, errorTitle='Invalid Grade',
        error='Please enter a grade from 6-12.'
    )
    grade_dv.sqref = 'C2:C1000'
    ws.add_data_validation(grade_dv)

    # EL Status: Newcomer, LTEL, RFEP, EO
    el_dv = DataValidation(
        type='list', formula1='"Newcomer,LTEL,RFEP,EO"', allow_blank=True,
        showErrorMessage=True, errorTitle='Invalid EL Status',
        error='Please choose: Newcomer, LTEL, RFEP, or EO'
    )
    el_dv.sqref = 'F2:F1000'
    ws.add_data_validation(el_dv)

    # EL Level: EL 1, EL 2, EL 3 (only for Newcomers)
    level_dv = DataValidation(
        type='list', formula1='"EL 1,EL 2,EL 3"', allow_blank=True,
        showErrorMessage=True, errorTitle='Invalid EL Level',
        error='Please choose: EL 1, EL 2, or EL 3 (only for Newcomer students)'
    )
    level_dv.sqref = 'G2:G1000'
    ws.add_data_validation(level_dv)

    # IEP: Yes or blank
    iep_dv = DataValidation(
        type='list', formula1='"Yes"', allow_blank=True,
        showErrorMessage=True, errorTitle='Invalid IEP',
        error='Enter "Yes" or leave blank.'
    )
    iep_dv.sqref = 'H2:H1000'
    ws.add_data_validation(iep_dv)

    # 504: Yes or blank
    plan_dv = DataValidation(
        type='list', formula1='"Yes"', allow_blank=True,
        showErrorMessage=True, errorTitle='Invalid 504 Plan',
        error='Enter "Yes" or leave blank.'
    )
    plan_dv.sqref = 'I2:I1000'
    ws.add_data_validation(plan_dv)

    # --- Format data rows (light alternating) ---
    alt_fill = PatternFill(start_color='F0F6FF', end_color='F0F6FF', fill_type='solid')
    for row in range(2, 52):  # Pre-format 50 rows
        for col_idx in range(1, len(columns) + 1):
            cell = ws.cell(row=row, column=col_idx)
            cell.border = thin_border
            cell.protection = unlocked
            cell.alignment = Alignment(vertical='center')
            if row % 2 == 0:
                cell.fill = alt_fill

    # --- Instructions sheet ---
    instr = wb.create_sheet('Instructions')
    instr.sheet_properties.tabColor = 'E8A838'

    instructions = [
        ('CASELOAD UPLOAD TEMPLATE - INSTRUCTIONS', ''),
        ('', ''),
        ('Column', 'Instructions'),
        ('First Name', 'Required. Student\'s first name.'),
        ('Last Name', 'Required. Student\'s last name.'),
        ('Grade', 'Required. Grade level from 6-12. Use the dropdown.'),
        ('Student ID #', 'Required. Must be unique. This is the school\'s student ID number.'),
        ('Email', 'Optional. Student email address.'),
        ('EL Status', 'Required. Choose from dropdown: Newcomer, LTEL, RFEP, or EO (English Only).'),
        ('EL Level', 'Only fill in if EL Status is "Newcomer". Choose: EL 1, EL 2, or EL 3.'),
        ('IEP', 'Enter "Yes" if student has an IEP. Otherwise leave blank.'),
        ('504 Plan', 'Enter "Yes" if student has a 504 Plan. Otherwise leave blank.'),
        ('', ''),
        ('NOTES:', ''),
        ('', 'Duplicate Student IDs will update the existing student record (not create duplicates).'),
        ('', 'EL Level is ONLY for Newcomer students. It will be ignored for other EL statuses.'),
        ('', 'All data stays local on your computer. Nothing is uploaded to the cloud.'),
    ]

    title_font = Font(name='Calibri', bold=True, size=14, color='2C5F8A')
    bold_font = Font(name='Calibri', bold=True, size=11)
    normal_font = Font(name='Calibri', size=11)

    for row_idx, (col_a, col_b) in enumerate(instructions, 1):
        cell_a = instr.cell(row=row_idx, column=1, value=col_a)
        cell_b = instr.cell(row=row_idx, column=2, value=col_b)
        if row_idx == 1:
            cell_a.font = title_font
        elif row_idx == 3:
            cell_a.font = bold_font
            cell_b.font = bold_font
        else:
            cell_a.font = bold_font if col_a else normal_font
            cell_b.font = normal_font

    instr.column_dimensions['A'].width = 18
    instr.column_dimensions['B'].width = 75

    # --- Freeze top row and protect ---
    ws.freeze_panes = 'A2'
    ws.sheet_protection.sheet = True
    ws.sheet_protection.formatCells = False
    ws.sheet_protection.insertRows = False
    ws.sheet_protection.sort = False
    ws.sheet_protection.autoFilter = False

    # Save to buffer
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    log_action('export', 'caseload_template', details='Downloaded caseload template')

    return send_file(
        buffer,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='Caseload_Upload_Template.xlsx'
    )


# =====================================================================
#  EXCEL UPLOAD
# =====================================================================

@caseload_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_caseload():
    if request.method == 'POST':
        file = request.files.get('file')
        if not file or not file.filename.endswith(('.xlsx', '.xls')):
            flash('Please upload an Excel file (.xlsx).', 'danger')
            return redirect(url_for('caseload.upload_caseload'))

        try:
            wb = load_workbook(file, data_only=True)
            ws = wb.active
        except Exception as e:
            flash(f'Could not read Excel file: {str(e)}', 'danger')
            return redirect(url_for('caseload.upload_caseload'))

        # Validate headers
        expected = ['first name', 'last name', 'grade', 'student id #', 'email',
                    'el status', 'el level', 'iep', '504 plan']
        headers = [str(cell.value or '').strip().lower() for cell in ws[1]]

        if headers[:len(expected)] != expected:
            flash(
                'Column headers don\'t match the template. Please download a fresh template and try again.',
                'danger'
            )
            return redirect(url_for('caseload.upload_caseload'))

        # Parse rows
        added = 0
        updated = 0
        errors = []

        for row_idx, row in enumerate(ws.iter_rows(min_row=2, max_col=9, values_only=True), start=2):
            first_name, last_name, grade, student_id, email, el_status, el_level, iep, plan_504 = row

            # Skip empty rows
            if not first_name and not last_name and not student_id:
                continue

            # Validate required fields
            row_errors = []
            if not first_name:
                row_errors.append('First Name is required')
            if not last_name:
                row_errors.append('Last Name is required')
            if not student_id:
                row_errors.append('Student ID # is required')
            if not grade:
                row_errors.append('Grade is required')

            # Validate grade
            grade_val = None
            if grade:
                try:
                    grade_val = int(grade)
                    if grade_val < 6 or grade_val > 12:
                        row_errors.append(f'Grade must be 6-12, got {grade_val}')
                except (ValueError, TypeError):
                    row_errors.append(f'Invalid grade: {grade}')

            # Normalize EL status
            el_status_clean = str(el_status or '').strip()
            if el_status_clean and el_status_clean not in VALID_EL_STATUSES:
                row_errors.append(f'Invalid EL Status: {el_status_clean}. Must be Newcomer, LTEL, RFEP, or EO.')
            if not el_status_clean:
                el_status_clean = 'EO'

            # Normalize EL level
            el_level_clean = str(el_level or '').strip()
            if el_status_clean == 'Newcomer' and el_level_clean and el_level_clean not in VALID_EL_LEVELS:
                row_errors.append(f'Invalid EL Level: {el_level_clean}. Must be EL 1, EL 2, or EL 3.')
            if el_status_clean != 'Newcomer':
                el_level_clean = ''

            # Normalize IEP / 504
            iep_bool = str(iep or '').strip().lower() in ('yes', 'y', 'true', '1')
            plan_504_bool = str(plan_504 or '').strip().lower() in ('yes', 'y', 'true', '1')

            if row_errors:
                errors.append(f'Row {row_idx}: ' + '; '.join(row_errors))
                continue

            # Upsert: update if student ID already exists
            student_id_str = str(student_id).strip()
            existing = Student.query.filter_by(student_id_number=student_id_str).first()

            if existing:
                existing.first_name = str(first_name).strip()
                existing.last_name = str(last_name).strip()
                existing.grade_level = grade_val
                existing.email = str(email or '').strip()
                existing.el_status = el_status_clean
                existing.el_level = el_level_clean
                existing.ell_status = (el_status_clean in ('Newcomer', 'LTEL', 'RFEP'))
                existing.iep_status = iep_bool
                existing.section_504 = plan_504_bool
                existing.assigned_counselor_id = current_user.id
                updated += 1
            else:
                student = Student(
                    student_id_number=student_id_str,
                    first_name=str(first_name).strip(),
                    last_name=str(last_name).strip(),
                    grade_level=grade_val,
                    email=str(email or '').strip(),
                    el_status=el_status_clean,
                    el_level=el_level_clean,
                    ell_status=(el_status_clean in ('Newcomer', 'LTEL', 'RFEP')),
                    iep_status=iep_bool,
                    section_504=plan_504_bool,
                    assigned_counselor_id=current_user.id,
                    status='active',
                )
                db.session.add(student)
                added += 1

        db.session.commit()
        log_action('import', 'caseload', details=f'Imported caseload: {added} added, {updated} updated')

        if errors:
            flash(f'Imported with issues: {added} added, {updated} updated, {len(errors)} errors.', 'warning')
            return render_template('caseload/upload.html', errors=errors, added=added, updated=updated)
        else:
            flash(f'Caseload imported successfully! {added} students added, {updated} updated.', 'success')
            return redirect(url_for('caseload.index'))

    return render_template('caseload/upload.html', errors=None, added=0, updated=0)


# =====================================================================
#  EXPORT CURRENT CASELOAD TO EXCEL
# =====================================================================

@caseload_bp.route('/export')
@login_required
def export_caseload():
    """Export current caseload to Excel."""
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id
    ).order_by(Student.grade_level, Student.last_name).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "My Caseload"

    header_font = Font(name='Calibri', bold=True, size=11, color='FFFFFF')
    header_fill = PatternFill(start_color='2C5F8A', end_color='2C5F8A', fill_type='solid')
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin'),
    )

    headers = ['First Name', 'Last Name', 'Grade', 'Student ID #', 'Email',
               'EL Status', 'EL Level', 'IEP', '504 Plan', 'Status']
    widths = [18, 18, 8, 16, 30, 16, 12, 8, 10, 12]

    for col_idx, (name, width) in enumerate(zip(headers, widths), 1):
        cell = ws.cell(row=1, column=col_idx, value=name)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = thin_border
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    for row_idx, s in enumerate(students, 2):
        values = [
            s.first_name, s.last_name, s.grade_level, s.student_id_number,
            s.email, s.el_status or 'EO', s.el_level or '',
            'Yes' if s.iep_status else '', 'Yes' if s.section_504 else '',
            s.status,
        ]
        for col_idx, val in enumerate(values, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.border = thin_border

    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = ws.dimensions

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    log_action('export', 'caseload', details=f'Exported {len(students)} students')

    return send_file(
        buffer,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='My_Caseload_Export.xlsx'
    )
