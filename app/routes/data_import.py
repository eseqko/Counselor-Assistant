"""Routes for importing attendance, grades, and other student data via CSV/Excel."""
import io
import csv
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
from app import db
from app.models.student import Student
from app.models.attendance import AttendanceRecord
from app.models.grade import GradeRecord
from app.utils.audit import log_action
from app.utils.helpers import parse_date
from datetime import date

try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

data_import_bp = Blueprint('data_import', __name__)

VALID_ATTENDANCE = {'present', 'absent', 'tardy', 'excused'}
VALID_GRADES = {'A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-',
                'D+', 'D', 'D-', 'F', 'P', 'NP', 'I', 'W'}

# Synergy SIS attendance code → (status, reason)
SYNERGY_STATUS_MAP = {
    '':                 ('present', ''),
    'activity':         ('excused', 'Activity'),
    'illness':          ('excused', 'Illness'),
    'excused':          ('excused', 'Excused'),
    'counseling':       ('excused', 'Counseling'),
    'testing':          ('excused', 'Testing'),
    'office excused':   ('excused', 'Office Excused'),
    'office ex':        ('excused', 'Office Excused'),
    'cut':              ('absent', 'Cut'),
    'unverified':       ('absent', 'Unverified'),
    'parent unexcused': ('absent', 'Parent Unexcused'),
    'tardy':            ('tardy', 'Tardy'),
    'unexcused tardy':  ('tardy', 'Unexcused Tardy'),
}


# =====================================================================
#  MAIN IMPORT HUB
# =====================================================================

@data_import_bp.route('/')
@login_required
def index():
    """Data import hub page."""
    # Count existing records
    student_ids = [s.id for s in Student.query.filter_by(
        assigned_counselor_id=current_user.id).all()]
    attendance_count = AttendanceRecord.query.filter(
        AttendanceRecord.student_id.in_(student_ids)).count() if student_ids else 0
    grade_count = GradeRecord.query.filter(
        GradeRecord.student_id.in_(student_ids)).count() if student_ids else 0
    return render_template('data_import/index.html',
                           attendance_count=attendance_count,
                           grade_count=grade_count)


# =====================================================================
#  ATTENDANCE IMPORT
# =====================================================================

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

        header, rows = _parse_upload_file(file)
        if header is None:
            return redirect(url_for('data_import.attendance_upload'))

        # Auto-detect Synergy format and convert to standard rows
        is_synergy = _is_synergy_format(header)
        if is_synergy:
            rows = _convert_synergy_rows(header, rows)
            if rows is None:
                flash('Could not parse Synergy file. Check that it has Perm ID, Date, and Period columns.', 'danger')
                return redirect(url_for('data_import.attendance_upload'))

        added = 0
        skipped = 0
        not_on_caseload = 0
        errors = []
        BATCH_SIZE = 200

        # Pre-load student lookup cache to avoid per-row DB queries
        student_cache = {
            s.student_id_number: s.id
            for s in Student.query.with_entities(
                Student.student_id_number, Student.id).all()
        }

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
                # For Synergy whole-school reports, silently skip non-caseload students
                if is_synergy:
                    not_on_caseload += 1
                    continue
                errors.append(f'Row {row_idx}: Student ID {student_id_str} not found')
                continue

            # Skip duplicates
            existing = AttendanceRecord.query.filter_by(
                student_id=student_db_id, date=att_date, period=period_val).first()
            if existing:
                skipped += 1
                continue

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

            # Batch commit to avoid holding SQLite lock too long
            if added % BATCH_SIZE == 0:
                db.session.commit()

        db.session.commit()
        log_action('import', 'attendance',
                   details=f'Imported attendance: {added} added, {skipped} skipped'
                           + (f', {not_on_caseload} not on caseload' if not_on_caseload else ''))

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


# =====================================================================
#  GRADES IMPORT
# =====================================================================

@data_import_bp.route('/grades/template')
@login_required
def grades_template():
    """Download grades import Excel template."""
    if not HAS_OPENPYXL:
        flash('Excel support requires openpyxl.', 'danger')
        return redirect(url_for('data_import.index'))

    wb = Workbook()
    ws = wb.active
    ws.title = "Grades Import"

    header_font = Font(name='Calibri', bold=True, size=11, color='FFFFFF')
    header_fill = PatternFill(start_color='2C5F8A', end_color='2C5F8A', fill_type='solid')
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin'),
    )

    columns = [
        ('Student ID #', 16),
        ('School Year', 12),
        ('Quarter', 8),
        ('Semester', 10),
        ('Period', 8),
        ('Course Name', 30),
        ('Course Number', 14),
        ('Subject Area', 20),
        ('Letter Grade', 12),
        ('Percent', 10),
        ('Credits Earned', 14),
        ('a-g?', 8),
        ('Honors/AP?', 12),
        ('CTE?', 8),
    ]

    for col_idx, (name, width) in enumerate(columns, 1):
        cell = ws.cell(row=1, column=col_idx, value=name)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = thin_border
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    # Validations
    quarter_dv = DataValidation(
        type='list', formula1='"1,2,3,4"', allow_blank=True,
        showErrorMessage=True, errorTitle='Invalid Quarter', error='Enter 1-4')
    quarter_dv.sqref = 'C2:C5000'
    ws.add_data_validation(quarter_dv)

    semester_dv = DataValidation(
        type='list', formula1='"1,2"', allow_blank=True,
        showErrorMessage=True, errorTitle='Invalid Semester', error='Enter 1 or 2')
    semester_dv.sqref = 'D2:D5000'
    ws.add_data_validation(semester_dv)

    grade_dv = DataValidation(
        type='list',
        formula1='"A+,A,A-,B+,B,B-,C+,C,C-,D+,D,D-,F,P,NP,I,W"',
        allow_blank=True, showErrorMessage=True, errorTitle='Invalid Grade',
        error='Enter a valid letter grade')
    grade_dv.sqref = 'I2:I5000'
    ws.add_data_validation(grade_dv)

    subject_dv = DataValidation(
        type='list',
        formula1='"English,Math,Science,History/Social Science,Fine Arts/LOTE,CTE,PE,Health,Electives"',
        allow_blank=True, showErrorMessage=True, errorTitle='Invalid Subject',
        error='Choose a valid subject area')
    subject_dv.sqref = 'H2:H5000'
    ws.add_data_validation(subject_dv)

    yesno_dv = DataValidation(
        type='list', formula1='"Yes"', allow_blank=True)
    for col_letter in ['L', 'M', 'N']:
        dv = DataValidation(type='list', formula1='"Yes"', allow_blank=True)
        dv.sqref = f'{col_letter}2:{col_letter}5000'
        ws.add_data_validation(dv)

    # Instructions
    instr = wb.create_sheet('Instructions')
    instr.sheet_properties.tabColor = 'E8A838'
    instructions = [
        ('GRADES IMPORT TEMPLATE — 4x4 BELL SCHEDULE', ''),
        ('', ''),
        ('Your school runs a 4x4 bell schedule:', ''),
        ('', '4 classes per quarter, 5 credits each'),
        ('', 'Semester 1 & 2 classes per term, classes change after Q2'),
        ('', '8 total classes per year (4 per term)'),
        ('', ''),
        ('Column', 'Instructions'),
        ('Student ID #', 'Required. Must match a student in your caseload.'),
        ('School Year', 'e.g., 2025-2026. Helps track year-over-year trends.'),
        ('Quarter', 'Which quarter: 1, 2, 3, or 4.'),
        ('Semester', '1 or 2. Q1-Q2 = Semester 1 classes. Q3-Q4 = Semester 2 classes.'),
        ('Period', 'Class period 1-4.'),
        ('Course Name', 'Required. Full course title.'),
        ('Course Number', 'Optional. Matches to your Course Catalog if available.'),
        ('Subject Area', 'English, Math, Science, etc. Helps with grad requirement tracking.'),
        ('Letter Grade', 'A+ through F, or P/NP/I/W.'),
        ('Percent', 'Optional. Numeric grade (0-100).'),
        ('Credits Earned', 'Default 5 for your 4x4 schedule. Enter 0 if failed/incomplete.'),
        ('a-g?', 'Yes if this course is UC a-g approved.'),
        ('Honors/AP?', 'Yes if Honors, AP, or IB course.'),
        ('CTE?', 'Yes if Career Technical Education course.'),
        ('', ''),
        ('TIPS:', ''),
        ('', 'You can export grades from Synergy/Aeries/PowerSchool and reformat to match.'),
        ('', 'One row per student per course per quarter.'),
        ('', 'The AI will use this data to recommend courses for next year.'),
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

    log_action('export', 'grades_template', details='Downloaded grades template')
    return send_file(buffer,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name='Grades_Import_Template.xlsx')


@data_import_bp.route('/grades/upload', methods=['GET', 'POST'])
@login_required
def grades_upload():
    """Upload grades data from Excel or CSV."""
    if request.method == 'POST':
        file = request.files.get('file')
        if not file:
            flash('Please select a file.', 'danger')
            return redirect(url_for('data_import.grades_upload'))

        _header, rows = _parse_upload_file(file)
        if rows is None:
            return redirect(url_for('data_import.grades_upload'))

        added = 0
        updated = 0
        errors = []

        for row_idx, row in enumerate(rows, start=2):
            if len(row) < 14:
                row.extend([''] * (14 - len(row)))
            (student_id_str, school_year, quarter_str, semester_str, period_str,
             course_name, course_number, subject_area, letter_grade,
             percent_str, credits_str, ag_str, honors_str, cte_str) = row[:14]

            if not student_id_str and not course_name:
                continue

            row_errors = []
            if not student_id_str:
                row_errors.append('Student ID # required')
            if not course_name:
                row_errors.append('Course Name required')

            # Parse quarter
            quarter_val = None
            if quarter_str:
                try:
                    quarter_val = int(quarter_str)
                    if quarter_val < 1 or quarter_val > 4:
                        row_errors.append(f'Quarter must be 1-4')
                except (ValueError, TypeError):
                    row_errors.append(f'Invalid quarter: {quarter_str}')

            # Parse semester
            semester_val = 1
            if semester_str:
                try:
                    semester_val = int(semester_str)
                    if semester_val not in (1, 2):
                        row_errors.append('Semester must be 1 or 2')
                except (ValueError, TypeError):
                    row_errors.append(f'Invalid semester: {semester_str}')

            # Parse period
            period_val = None
            if period_str:
                try:
                    period_val = int(period_str)
                except (ValueError, TypeError):
                    pass

            # Parse percent
            percent_val = None
            if percent_str:
                try:
                    percent_val = float(percent_str)
                except (ValueError, TypeError):
                    pass

            # Parse credits (default 5 for 4x4)
            credits_val = 5.0
            if credits_str:
                try:
                    credits_val = float(credits_str)
                except (ValueError, TypeError):
                    pass

            # Validate letter grade
            letter_clean = str(letter_grade or '').strip()
            if letter_clean and letter_clean not in VALID_GRADES:
                row_errors.append(f'Invalid grade: {letter_clean}')

            if row_errors:
                errors.append(f'Row {row_idx}: ' + '; '.join(row_errors))
                continue

            student = Student.query.filter_by(
                student_id_number=str(student_id_str).strip()).first()
            if not student:
                errors.append(f'Row {row_idx}: Student ID {student_id_str} not found')
                continue

            # Upsert: update if same student+year+quarter+course
            course_name_clean = str(course_name).strip()
            school_year_clean = str(school_year or '').strip()
            existing = GradeRecord.query.filter_by(
                student_id=student.id,
                school_year=school_year_clean,
                quarter=quarter_val,
                course_name=course_name_clean,
            ).first()

            yes_vals = ('yes', 'y', 'true', '1')

            if existing:
                existing.letter_grade = letter_clean or existing.letter_grade
                existing.percent_grade = percent_val if percent_val is not None else existing.percent_grade
                existing.credits_earned = credits_val
                existing.subject_area = str(subject_area or '').strip() or existing.subject_area
                existing.is_ag = str(ag_str or '').strip().lower() in yes_vals
                existing.is_honors_ap = str(honors_str or '').strip().lower() in yes_vals
                existing.is_cte = str(cte_str or '').strip().lower() in yes_vals
                updated += 1
            else:
                record = GradeRecord(
                    student_id=student.id,
                    school_year=school_year_clean,
                    quarter=quarter_val,
                    course_name=course_name_clean,
                    course_number=str(course_number or '').strip(),
                    period=period_val,
                    letter_grade=letter_clean,
                    percent_grade=percent_val,
                    credits_earned=credits_val,
                    credits_attempted=5.0,
                    is_semester=semester_val,
                    subject_area=str(subject_area or '').strip(),
                    is_ag=str(ag_str or '').strip().lower() in yes_vals,
                    is_honors_ap=str(honors_str or '').strip().lower() in yes_vals,
                    is_cte=str(cte_str or '').strip().lower() in yes_vals,
                    imported_by_id=current_user.id,
                )
                db.session.add(record)
                added += 1

        db.session.commit()
        log_action('import', 'grades',
                   details=f'Imported grades: {added} added, {updated} updated')

        if errors:
            flash(f'Imported with issues: {added} added, {updated} updated, {len(errors)} errors.', 'warning')
        else:
            flash(f'Grades imported: {added} added, {updated} updated.', 'success')

        return render_template('data_import/grades_upload.html',
                               added=added, updated=updated, errors=errors)

    return render_template('data_import/grades_upload.html',
                           added=0, updated=0, errors=None)


# =====================================================================
#  CLEAR DATA
# =====================================================================

@data_import_bp.route('/attendance/clear', methods=['POST'])
@login_required
def clear_attendance():
    """Clear all attendance records for current counselor's students."""
    student_ids = [s.id for s in Student.query.filter_by(
        assigned_counselor_id=current_user.id).all()]
    count = AttendanceRecord.query.filter(
        AttendanceRecord.student_id.in_(student_ids)).delete(synchronize_session=False)
    db.session.commit()
    log_action('delete', 'attendance', details=f'Cleared {count} attendance records')
    flash(f'Cleared {count} attendance records.', 'warning')
    return redirect(url_for('data_import.index'))


@data_import_bp.route('/grades/clear', methods=['POST'])
@login_required
def clear_grades():
    """Clear all grade records for current counselor's students."""
    student_ids = [s.id for s in Student.query.filter_by(
        assigned_counselor_id=current_user.id).all()]
    count = GradeRecord.query.filter(
        GradeRecord.student_id.in_(student_ids)).delete(synchronize_session=False)
    db.session.commit()
    log_action('delete', 'grades', details=f'Cleared {count} grade records')
    flash(f'Cleared {count} grade records.', 'warning')
    return redirect(url_for('data_import.index'))


# =====================================================================
#  HELPERS
# =====================================================================

def _parse_upload_file(file):
    """Parse CSV or Excel file, return (header_row, data_rows).

    Returns (None, None) on error.  header_row is a list of strings
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


def _is_synergy_format(header):
    """Detect if the header row matches a Synergy attendance export."""
    if not header:
        return False
    header_lower = [h.strip().lower() for h in header]
    # Synergy reports have "period 0", "period 1", … as column headers
    return 'period 0' in header_lower or ('period 1' in header_lower and 'perm id' in header_lower)


def _convert_synergy_rows(header, rows):
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
