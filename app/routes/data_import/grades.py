"""Grades import: template download, preview, upload, clear."""
import io
from flask import render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_login import login_required, current_user
from app import db, csrf
from app.models.student import Student
from app.models.grade import GradeRecord
from app.models.import_log import ImportLog
from app.utils.audit import log_action
from datetime import date
from app.routes.data_import import (
    data_import_bp, HAS_OPENPYXL, VALID_GRADES,
    Workbook, Font, PatternFill, Alignment, Border, Side,
    get_column_letter, DataValidation,
)
from app.routes.data_import._parsers import (
    parse_upload_file, build_grade_col_map, col, parse_quarter,
)


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
        ('School Year', 14),
        ('Perm ID', 12),
        ('Grade Level', 12),
        ('Grade', 8),
        ('Mark Order', 12),
        ('Mark Name', 14),
        ('Course Title', 30),
        ('Course ID', 12),
        ('Period', 8),
        ('C1', 6),
        ('C2', 6),
        ('C3', 6),
        ('Staff Name', 20),
        ('Audit Class', 12),
        ('Student Name', 22),
        ('SPED', 8),
        ('SigDis', 8),
        ('SLE', 8),
    ]

    for col_idx, (name, width) in enumerate(columns, 1):
        cell = ws.cell(row=1, column=col_idx, value=name)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = thin_border
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    # Validations
    grade_dv = DataValidation(
        type='list',
        formula1='"A+,A,A-,B+,B,B-,C+,C,C-,D+,D,D-,F,P,NP,I,W"',
        allow_blank=True, showErrorMessage=True, errorTitle='Invalid Grade',
        error='Enter a valid letter grade')
    grade_dv.sqref = 'D2:D5000'
    ws.add_data_validation(grade_dv)

    audit_dv = DataValidation(
        type='list', formula1='"N,Y"', allow_blank=True)
    audit_dv.sqref = 'N2:N5000'
    ws.add_data_validation(audit_dv)

    # Instructions
    instr = wb.create_sheet('Instructions')
    instr.sheet_properties.tabColor = 'E8A838'
    instructions = [
        ('GRADES IMPORT TEMPLATE — SYNERGY FORMAT', ''),
        ('', ''),
        ('This template matches the Synergy SIS grade export.', ''),
        ('Export from Synergy and paste or upload directly.', ''),
        ('', ''),
        ('Column', 'Instructions'),
        ('School Year', 'e.g., 2025-2026.'),
        ('Perm ID', 'Required. Student permanent ID — must match a student in your caseload.'),
        ('Grade Level', 'Student grade level (9, 10, 11, 12). Informational.'),
        ('Grade', 'Required. Letter grade (A+, A, A-, B+, … F, P, NP, I, W).'),
        ('Mark Order', 'Numeric mark sequence (1, 2, etc.). Optional.'),
        ('Mark Name', 'e.g., "Quarter 3". The quarter number is extracted automatically.'),
        ('Course Title', 'Required. Full course title from Synergy (e.g., "Spanish 1 CP [S1]").'),
        ('Course ID', 'Synergy course ID number. Used to match to your Course Catalog.'),
        ('Period', 'Class period (1-4).'),
        ('C1, C2, C3', 'Citizenship grades. Stored for reference but not analyzed.'),
        ('Staff Name', 'Teacher name. Stored for reference.'),
        ('Audit Class', 'N or Y. Audit classes are skipped during import.'),
        ('Student Name', 'For reference. Not used for matching (Perm ID is used).'),
        ('SPED', 'Special education flag. Informational.'),
        ('SigDis', 'Significant disability flag. Informational.'),
        ('SLE', 'Structured Learning Experience flag. Informational.'),
        ('', ''),
        ('TIPS:', ''),
        ('', 'You can paste your Synergy export directly — no reformatting needed.'),
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


@data_import_bp.route('/grades/preview', methods=['POST'])
@csrf.exempt
@login_required
def grades_preview():
    """AJAX endpoint: parse uploaded file and return preview JSON."""
    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'No file provided'}), 400

    _header, rows = parse_upload_file(file)
    if _header is None:
        return jsonify({'error': 'Could not read file'}), 400

    col_map = build_grade_col_map(_header)
    header_quarter = col_map.get('_quarter_from_header')

    # Detect columns found
    detected = {}
    for key in ('perm_id', 'grade', 'course_title', 'period', 'credits_att',
                'grade_level', 'staff_name', 'student_name', 'school_year'):
        if key in col_map:
            idx = col_map[key]
            detected[key] = _header[idx] if idx < len(_header) else key

    # Count students on caseload vs not
    id_cache = {
        s.student_id_number: True
        for s in Student.query.with_entities(Student.student_id_number).all()
    }
    # Also build name-based lookup for fallback
    name_cache = {}
    for s in Student.query.with_entities(Student.last_name, Student.first_name, Student.student_id_number).all():
        key = f"{s.last_name.strip().lower()}, {s.first_name.strip().lower()}"
        name_cache[key] = s.student_id_number

    total_rows = 0
    matched = 0
    unmatched = 0
    empty_grade = 0
    sample_rows = []

    for row in rows:
        while len(row) < 16:
            row.append('')
        sid = col(row, col_map, 'perm_id')
        grade_val = col(row, col_map, 'grade')
        course = col(row, col_map, 'course_title')
        student_name = col(row, col_map, 'student_name')

        if not sid and not course:
            continue
        total_rows += 1

        if not grade_val:
            empty_grade += 1
            continue

        found = id_cache.get(str(sid).strip())
        if not found and student_name:
            found = student_name.strip().lower() in name_cache
        if found:
            matched += 1
        else:
            unmatched += 1

        if len(sample_rows) < 5:
            sample_rows.append({
                'student': student_name or sid,
                'course': course,
                'grade': grade_val,
                'matched': bool(found),
            })

    # Build current school year default
    now = date.today()
    yr = now.year if now.month >= 7 else now.year - 1
    default_school_year = f"{yr}-{yr + 1}"

    return jsonify({
        'columns': detected,
        'quarter': header_quarter,
        'total_rows': total_rows,
        'matched': matched,
        'unmatched': unmatched,
        'empty_grade': empty_grade,
        'sample': sample_rows,
        'default_school_year': default_school_year,
    })


@data_import_bp.route('/grades/upload', methods=['GET', 'POST'])
@login_required
def grades_upload():
    """Upload grades data from Excel or CSV."""
    # Build school year options for the dropdown
    now = date.today()
    yr = now.year if now.month >= 7 else now.year - 1
    school_year_options = [f"{y}-{y + 1}" for y in range(yr, yr - 4, -1)]
    default_school_year = school_year_options[0]

    if request.method == 'POST':
        file = request.files.get('file')
        if not file:
            flash('Please select a file.', 'danger')
            return redirect(url_for('data_import.grades_upload'))

        # School year from form (since Synergy doesn't include it)
        form_school_year = request.form.get('school_year', '').strip() or default_school_year
        # Grade type: 'final' (quarter grades) or 'progress' (mid-quarter progress report)
        form_grade_type = request.form.get('grade_type', 'final').strip()
        if form_grade_type not in ('final', 'progress'):
            form_grade_type = 'final'

        _header, rows = parse_upload_file(file)
        if rows is None:
            return redirect(url_for('data_import.grades_upload'))

        added = 0
        updated = 0
        skipped = 0
        not_on_caseload = 0
        errors = []
        BATCH_SIZE = 200

        # Pre-load student lookup caches
        student_cache = {
            s.student_id_number: s.id
            for s in Student.query.with_entities(
                Student.student_id_number, Student.id).all()
        }
        # Name-based fallback: "last, first" → student_id_number
        name_to_sid = {}
        for s in Student.query.with_entities(
                Student.last_name, Student.first_name, Student.student_id_number).all():
            key = f"{s.last_name.strip().lower()}, {s.first_name.strip().lower()}"
            name_to_sid[key] = s.student_id_number

        # Build column index from header row
        col_map = build_grade_col_map(_header)

        # Quarter may come from the header name (e.g., "Quarter 3" column)
        header_quarter = col_map.pop('_quarter_from_header', None)

        # Auto-purge: when importing FINAL grades, delete progress report grades
        # for the same quarter/year/students
        purged = 0
        if form_grade_type == 'final' and header_quarter and form_school_year:
            purged = GradeRecord.query.filter_by(
                school_year=form_school_year,
                quarter=header_quarter,
                grade_type='progress',
            ).delete(synchronize_session=False)
            if purged:
                db.session.commit()

        for row_idx, row in enumerate(rows, start=2):
            # Pad short rows
            while len(row) < 16:
                row.append('')

            # Extract values by mapped column positions
            student_id_str = col(row, col_map, 'perm_id')
            school_year = col(row, col_map, 'school_year') or form_school_year
            letter_grade = col(row, col_map, 'grade')
            mark_name = col(row, col_map, 'mark_name')
            course_name = col(row, col_map, 'course_title')
            course_number = col(row, col_map, 'course_id')
            period_str = col(row, col_map, 'period')
            audit_class = col(row, col_map, 'audit_class')
            credits_att = col(row, col_map, 'credits_att')
            student_name = col(row, col_map, 'student_name')

            if not student_id_str and not course_name:
                continue

            # Skip audit classes
            if str(audit_class).strip().upper() == 'Y':
                skipped += 1
                continue

            row_errors = []
            if not student_id_str and not student_name:
                row_errors.append('Perm ID or Student Name required')
            if not course_name:
                row_errors.append('Course Title required')

            # ── Determine quarter ──
            # Priority: header name ("Quarter 3" column) > mark_name field > None
            quarter_val = header_quarter or parse_quarter(mark_name)

            # Derive semester from quarter (Q1-Q2 = Sem 1, Q3-Q4 = Sem 2)
            semester_val = 2 if quarter_val and quarter_val >= 3 else 1

            # ── Parse period ──
            # Synergy grade reports may have Period column or Section ID like "1-010"
            period_val = None
            if period_str:
                try:
                    period_val = int(float(period_str))
                except (ValueError, TypeError):
                    pass
            # If no Period column but Section ID has "1-010" format, extract period
            if period_val is None and course_number and '-' in str(course_number):
                try:
                    period_val = int(str(course_number).split('-')[0])
                except (ValueError, TypeError):
                    pass

            # ── Parse per-course credits ──
            credits_val = 5.0
            if credits_att:
                try:
                    credits_val = float(credits_att)
                except (ValueError, TypeError):
                    pass

            # Validate letter grade
            letter_clean = str(letter_grade or '').strip()
            if letter_clean and letter_clean not in VALID_GRADES:
                row_errors.append(f'Invalid grade: {letter_clean}')

            if row_errors:
                errors.append(f'Row {row_idx}: ' + '; '.join(row_errors))
                continue

            # Skip rows with no letter grade (empty grade cell)
            if not letter_clean:
                skipped += 1
                continue

            # ── Resolve student: Perm ID first, then name fallback ──
            sid_clean = str(student_id_str).strip()
            student_db_id = student_cache.get(sid_clean)

            if not student_db_id and student_name:
                # Try "Last, First" name matching
                name_key = student_name.strip().lower()
                fallback_sid = name_to_sid.get(name_key)
                if fallback_sid:
                    student_db_id = student_cache.get(fallback_sid)

            if not student_db_id:
                not_on_caseload += 1
                continue

            # Detect honors/AP from course title
            course_title_clean = str(course_name).strip()
            title_upper = course_title_clean.upper()
            is_honors_ap = 'AP ' in title_upper or title_upper.startswith('AP ') or ' HONORS' in title_upper

            # Upsert: update if same student+year+quarter+course
            school_year_clean = str(school_year or '').strip()
            existing = GradeRecord.query.filter_by(
                student_id=student_db_id,
                school_year=school_year_clean,
                quarter=quarter_val,
                course_name=course_title_clean,
                grade_type=form_grade_type,
            ).first()

            if existing:
                existing.letter_grade = letter_clean or existing.letter_grade
                existing.course_number = str(course_number or '').strip() or existing.course_number
                existing.is_honors_ap = is_honors_ap
                existing.credits_earned = credits_val
                updated += 1
            else:
                record = GradeRecord(
                    student_id=student_db_id,
                    school_year=school_year_clean,
                    quarter=quarter_val,
                    course_name=course_title_clean,
                    course_number=str(course_number or '').strip(),
                    period=period_val,
                    letter_grade=letter_clean,
                    grade_type=form_grade_type,
                    credits_earned=credits_val,
                    credits_attempted=credits_val,
                    is_semester=semester_val,
                    is_honors_ap=is_honors_ap,
                    imported_by_id=current_user.id,
                )
                db.session.add(record)
                added += 1

            # Batch commit to avoid holding SQLite lock too long
            if (added + updated) % BATCH_SIZE == 0:
                db.session.commit()

        db.session.commit()
        log_action('import', 'grades',
                   details=f'Imported {form_grade_type} grades: {added} added, {updated} updated'
                           + (f', {not_on_caseload} not on caseload' if not_on_caseload else '')
                           + (f', {purged} progress grades replaced' if purged else ''))

        # Log the import
        db.session.add(ImportLog(
            user_id=current_user.id, import_type='grades',
            grade_type=form_grade_type, school_year=form_school_year,
            quarter=header_quarter,
            records_added=added, records_updated=updated,
            records_skipped=not_on_caseload, errors_count=len(errors)))
        db.session.commit()

        grade_label = 'Progress report' if form_grade_type == 'progress' else 'Quarter'
        if purged:
            flash(f'{purged} progress report grades replaced with final grades.', 'info')
        if not_on_caseload:
            msg = f'{grade_label} grades: {added} added, {updated} updated. {not_on_caseload} not on caseload (skipped).'
        else:
            msg = f'{grade_label} grades: {added} added, {updated} updated.'

        if errors:
            flash(f'Imported with issues: {msg} {len(errors)} errors.', 'warning')
        else:
            flash(f'Grades imported: {msg}', 'success')

        return render_template('data_import/grades_upload.html',
                               added=added, updated=updated, errors=errors,
                               school_year_options=school_year_options,
                               default_school_year=form_school_year)

    return render_template('data_import/grades_upload.html',
                           added=0, updated=0, errors=None,
                           school_year_options=school_year_options,
                           default_school_year=default_school_year)


@data_import_bp.route('/grades/clear', methods=['POST'])
@login_required
def clear_grades():
    """Clear all grade records for current counselor's students."""
    student_ids = [row[0] for row in Student.query.filter_by(
        assigned_counselor_id=current_user.id).with_entities(Student.id).all()]
    count = GradeRecord.query.filter(
        GradeRecord.student_id.in_(student_ids)).delete(synchronize_session=False)
    db.session.commit()
    log_action('delete', 'grades', details=f'Cleared {count} grade records')
    flash(f'Cleared {count} grade records.', 'warning')
    return redirect(url_for('data_import.index'))
