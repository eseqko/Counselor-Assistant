"""Grades import: template download, preview, upload, clear."""
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db, csrf
from app.models.student import Student
from app.models.grade import GradeRecord
from app.models.import_log import ImportLog
from app.utils.audit import log_action
from app.utils.excel_helpers import build_import_workbook, workbook_response
from app.utils.caseload import caseload_student_ids
from app.utils.helpers import current_school_year
from datetime import date
from app.routes.data_import import (
    data_import_bp, HAS_OPENPYXL, VALID_GRADES,
    Workbook, Font, PatternFill, Alignment, Border, Side,
    get_column_letter, DataValidation,
)
from app.routes.data_import._parsers import (
    parse_upload_file, build_grade_col_map, col, parse_quarter,
    expand_quarter_columns,
)


_OPENPYXL_KIT = {
    'Workbook': Workbook, 'Font': Font, 'PatternFill': PatternFill,
    'Alignment': Alignment, 'Border': Border, 'Side': Side,
    'get_column_letter': get_column_letter, 'DataValidation': DataValidation,
}


@data_import_bp.route('/grades/template')
@login_required
def grades_template():
    """Download grades import Excel template."""
    if not HAS_OPENPYXL:
        flash('Excel support requires openpyxl.', 'danger')
        return redirect(url_for('data_import.index'))

    wb = build_import_workbook(
        _OPENPYXL_KIT,
        sheet_title='Grades Import',
        header_wrap=True,
        columns=[
            ('School Year', 14),
            ('Perm ID', 12),
            ('Grade Level', 12),
            ('Grade', 8),
            ('Mark Order', 12),
            ('Mark Name', 14),
            ('Course Title', 30),
            ('Course ID', 12),
            ('Period', 8),
            ('C1', 6), ('C2', 6), ('C3', 6),
            ('Staff Name', 20),
            ('Audit Class', 12),
            ('Student Name', 22),
            ('SPED', 8), ('SigDis', 8), ('SLE', 8),
        ],
        validations=[
            {'formula1': '"A+,A,A-,B+,B,B-,C+,C,C-,D+,D,D-,F,P,NP,I,W"',
             'sqref': 'D2:D5000', 'allow_blank': True,
             'error_title': 'Invalid Grade',
             'error_message': 'Enter a valid letter grade'},
            {'formula1': '"N,Y"', 'sqref': 'N2:N5000', 'allow_blank': True},
        ],
        instructions=[
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
        ],
    )

    log_action('export', 'grades_template', details='Downloaded grades template')
    return workbook_response(wb, 'Grades_Import_Template.xlsx')


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

    # A GRD401-style export carries one column per quarter; flatten it to one
    # row per grade before anything counts or maps columns.
    _header, rows = expand_quarter_columns(_header, rows)

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

    return jsonify({
        'columns': detected,
        'quarter': header_quarter,
        'total_rows': total_rows,
        'matched': matched,
        'unmatched': unmatched,
        'empty_grade': empty_grade,
        'sample': sample_rows,
        'default_school_year': current_school_year(),
    })


@data_import_bp.route('/grades/upload', methods=['GET', 'POST'])
@login_required
def grades_upload():
    """Upload grades data from Excel or CSV."""
    # Build school year options for the dropdown (current + 3 previous)
    now = date.today()
    base_yr = now.year if now.month >= 7 else now.year - 1
    school_year_options = [f"{y}-{y + 1}" for y in range(base_yr, base_yr - 4, -1)]
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

        # Same flattening as the preview, so what was previewed is what commits.
        _header, rows = expand_quarter_columns(_header, rows)

        added = 0
        updated = 0
        skipped = 0
        not_on_caseload = 0
        shadow_added = 0  # students created for school-wide comparison data
        errors = []
        # course_number -> teacher name, collected to backfill Course.instructor
        course_teacher = {}

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
        # A single-quarter export names its quarter in the header; a flattened
        # multi-quarter one carries a quarter per row, so collect those instead
        # or the superseded progress grades would survive for every quarter but
        # the first.
        purge_quarters = set()
        if header_quarter:
            purge_quarters.add(header_quarter)
        elif 'mark_name' in col_map:
            for row in rows:
                q = parse_quarter(col(row, col_map, 'mark_name'))
                if q:
                    purge_quarters.add(q)

        if form_grade_type == 'final' and purge_quarters and form_school_year:
            purged = GradeRecord.query.filter(
                GradeRecord.school_year == form_school_year,
                GradeRecord.quarter.in_(sorted(purge_quarters)),
                GradeRecord.grade_type == 'progress',
            ).delete(synchronize_session=False)
            if purged:
                db.session.commit()

        # ── Pre-load the upsert map ──────────────────────────────────────
        # The old code ran GradeRecord.query.filter_by(...).first() per CSV row:
        # 20k rows = 20k SELECTs + 20k autoflushes ≈ 25s of a 40s import in
        # profiling. Load every existing key for this grade_type ONCE as cheap
        # tuples, then upsert against in-memory dicts and write back with bulk
        # mappings at the end.
        #   key: (student_id, school_year, quarter, course_name)
        #   val: dict of the fields the conditional update logic needs
        db_map = {}
        for (gid, g_sid, g_year, g_quarter, g_course, g_letter, g_cnum,
             g_teacher) in db.session.query(
                GradeRecord.id, GradeRecord.student_id, GradeRecord.school_year,
                GradeRecord.quarter, GradeRecord.course_name,
                GradeRecord.letter_grade, GradeRecord.course_number,
                GradeRecord.teacher,
        ).filter(GradeRecord.grade_type == form_grade_type).all():
            db_map[(g_sid, g_year, g_quarter, g_course)] = {
                'id': gid, 'letter_grade': g_letter,
                'course_number': g_cnum, 'teacher': g_teacher,
            }
        pending_inserts = {}   # key -> insert dict (duplicate rows mutate in place)
        pending_updates = {}   # id  -> update dict

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
            teacher_clean = str(col(row, col_map, 'staff_name') or '').strip()

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
                # School-wide comparison data: create a "shadow" Student record so
                # the grade row isn't lost. Shadow students are filtered out of
                # every caseload UI (assigned_counselor_id=None + is_shadow=True),
                # surfaced only in aggregate analytics for "vs school" comparisons.
                # Requires a perm ID — name-only rows can't be deduped reliably.
                if sid_clean:
                    first_name = ''
                    last_name = ''
                    if student_name and ',' in student_name:
                        # Synergy format: "Last, First"
                        parts = [p.strip() for p in student_name.split(',', 1)]
                        last_name, first_name = parts[0], parts[1]
                    elif student_name:
                        first_name = student_name.strip()
                    shadow = Student(
                        student_id_number=sid_clean,
                        first_name=first_name or 'Unknown',
                        last_name=last_name or 'Student',
                        assigned_counselor_id=None,
                        status='active',
                        is_shadow=True,
                    )
                    db.session.add(shadow)
                    db.session.flush()  # need shadow.id for the grade record
                    student_db_id = shadow.id
                    student_cache[sid_clean] = shadow.id  # reuse for future rows
                    shadow_added += 1
                else:
                    not_on_caseload += 1
                    continue

            # Detect honors/AP from course title
            course_title_clean = str(course_name).strip()
            title_upper = course_title_clean.upper()
            is_honors_ap = 'AP ' in title_upper or title_upper.startswith('AP ') or ' HONORS' in title_upper

            # Upsert: update if same student+year+quarter+course (in-memory
            # maps — see preload above — written back in bulk after the loop)
            school_year_clean = str(school_year or '').strip()
            key = (student_db_id, school_year_clean, quarter_val, course_title_clean)
            cnum_clean = str(course_number or '').strip()

            existing = db_map.get(key)
            if existing is not None:
                upd = pending_updates.setdefault(existing['id'], {'id': existing['id']})
                # Same conditional semantics as the old per-row ORM update:
                # blank values never wipe existing data.
                upd['letter_grade'] = letter_clean or existing['letter_grade']
                upd['course_number'] = cnum_clean or existing['course_number']
                upd['is_honors_ap'] = is_honors_ap
                upd['credits_earned'] = credits_val
                if teacher_clean:
                    upd['teacher'] = teacher_clean
                # Keep the cache current so a later duplicate row in this same
                # file conditions against the freshest values.
                existing['letter_grade'] = upd['letter_grade']
                existing['course_number'] = upd['course_number']
                if teacher_clean:
                    existing['teacher'] = teacher_clean
                updated += 1
            elif key in pending_inserts:
                # Duplicate row in the same file: mutate the pending insert,
                # matching the old behavior where autoflush made the first
                # row's record visible to the second row's query.
                rec = pending_inserts[key]
                rec['letter_grade'] = letter_clean or rec['letter_grade']
                rec['course_number'] = cnum_clean or rec['course_number']
                rec['is_honors_ap'] = is_honors_ap
                rec['credits_earned'] = credits_val
                if teacher_clean:
                    rec['teacher'] = teacher_clean
                updated += 1
            else:
                pending_inserts[key] = dict(
                    student_id=student_db_id,
                    school_year=school_year_clean,
                    quarter=quarter_val,
                    course_name=course_title_clean,
                    course_number=cnum_clean,
                    period=period_val,
                    teacher=teacher_clean or None,
                    letter_grade=letter_clean,
                    grade_type=form_grade_type,
                    credits_earned=credits_val,
                    credits_attempted=credits_val,
                    is_semester=semester_val,
                    is_honors_ap=is_honors_ap,
                    imported_by_id=current_user.id,
                )
                added += 1

            # Remember the teacher for each catalog course number (backfill below).
            # Names are also auto-upserted into the Staff table after the loop so
            # the counselor can add email/phone/notes against a real record.
            cnum = str(course_number or '').strip()
            if cnum and teacher_clean:
                course_teacher.setdefault(cnum, teacher_clean)

        # Persist any shadow students created in the loop, then write all grade
        # rows in two bulk statements — orders of magnitude fewer round-trips
        # than per-row adds with periodic commits.
        db.session.commit()
        if pending_inserts:
            db.session.bulk_insert_mappings(GradeRecord, list(pending_inserts.values()))
        if pending_updates:
            db.session.bulk_update_mappings(GradeRecord, list(pending_updates.values()))
        db.session.commit()

        # Backfill Course.instructor from the staff names in this import, but only
        # where the catalog course has no instructor yet (never overwrite a
        # counselor's manual entry).
        backfilled = 0
        if course_teacher:
            from app.models.course import Course
            catalog = Course.query.filter(
                Course.course_number.in_(list(course_teacher.keys()))).all()
            for c in catalog:
                if not (c.instructor or '').strip():
                    c.instructor = course_teacher[c.course_number]
                    backfilled += 1
            if backfilled:
                db.session.commit()

        # Auto-upsert Staff records for every teacher name seen this import.
        # Match case-insensitively against existing names so "Ms. Rivera" doesn't
        # duplicate against "ms. rivera". Counselor's edits to email/notes survive.
        staff_added = 0
        all_teachers = {t for t in course_teacher.values()}
        # Also pull any teachers that appeared on rows without a course number
        for row in rows:
            t = str(col(row, col_map, 'staff_name') or '').strip()
            if t:
                all_teachers.add(t)
        if all_teachers:
            from app.models.staff import Staff
            existing_by_lower = {
                s.name.lower(): s for s in
                Staff.query.filter(db.func.lower(Staff.name).in_(
                    [t.lower() for t in all_teachers])).all()
            }
            for t in all_teachers:
                if t.lower() not in existing_by_lower:
                    db.session.add(Staff(name=t, title='Teacher'))
                    staff_added += 1
            if staff_added:
                db.session.commit()

        log_action('import', 'grades',
                   details=f'Imported {form_grade_type} grades: {added} added, {updated} updated'
                           + (f', {shadow_added} school-wide added' if shadow_added else '')
                           + (f', {not_on_caseload} unidentifiable' if not_on_caseload else '')
                           + (f', {purged} progress grades replaced' if purged else '')
                           + (f', {backfilled} course instructors set' if backfilled else '')
                           + (f', {staff_added} staff records created' if staff_added else ''))

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
        msg = f'{grade_label} grades: {added} added, {updated} updated.'
        if shadow_added:
            msg += f' {shadow_added} additional grades kept for school-wide comparison reports (students not on your caseload).'
        if not_on_caseload:
            msg += f' {not_on_caseload} rows skipped (no student ID).'

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
    student_ids = caseload_student_ids(current_user)
    count = GradeRecord.query.filter(
        GradeRecord.student_id.in_(student_ids)).delete(synchronize_session=False)
    db.session.commit()
    log_action('delete', 'grades', details=f'Cleared {count} grade records')
    flash(f'Cleared {count} grade records.', 'warning')
    return redirect(url_for('data_import.index'))
