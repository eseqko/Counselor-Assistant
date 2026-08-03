"""Import student class schedules from a Synergy export or a printed PDF.

Flow mirrors the other importers: upload -> PREVIEW -> confirm -> commit.
The preview matters more here than elsewhere, because the PDF path reads a
printout by column position and the counselor is the one who can tell at a
glance whether it read correctly.

Both file types funnel through app/utils/schedule_parser, which normalizes them
to the same row shape, so everything below is format-agnostic.
"""
import json
import os
import secrets
import time
from collections import defaultdict

from flask import (render_template, request, redirect, url_for, flash, session)
from flask_login import login_required, current_user

from app import db
from app.models.course import Course
from app.models.import_log import ImportLog
from app.models.schedule import ScheduleEntry
from app.models.staff import Staff
from app.models.student import Student
from app.routes.data_import import data_import_bp
from app.utils.audit import log_action
from app.utils.db_snapshot import snapshot_database
from app.utils.schedule_parser import parse_schedule_file
from app.utils.staff_directory import (
    apply_staff_records, derive_staff_from_schedule, summarize as summarize_staff)
from config import DATA_DIR

# The preview payload is staged in a FILE between the two requests, with only a
# short token kept in the session.
#
# It used to live in the session itself, which silently broke EVERY import:
# Flask's default session is a signed COOKIE capped at ~4KB, and a single
# student's 18 schedule rows serialise to ~6KB. Werkzeug refuses to set an
# oversized cookie without raising, so the key simply never came back and the
# confirm step always reported "That preview expired". A 200-student import is
# ~1.3MB, three hundred times the limit.
PREVIEW_KEY = 'schedule_preview_token'
PREVIEW_TTL_SECONDS = 3600


def _preview_dir():
    path = os.path.join(DATA_DIR, 'tmp')
    os.makedirs(path, exist_ok=True)
    return path


def _preview_path(token):
    # Tokens are generated here, never user-supplied, but constrain the name
    # anyway so a tampered session value can't escape the directory.
    safe = ''.join(c for c in (token or '') if c.isalnum() or c in '-_')
    if not safe:
        return None
    return os.path.join(_preview_dir(), f'schedule_preview_{safe}.json')


def _purge_stale_previews():
    """Drop abandoned preview files so they don't accumulate."""
    now = time.time()
    try:
        for name in os.listdir(_preview_dir()):
            if not name.startswith('schedule_preview_'):
                continue
            full = os.path.join(_preview_dir(), name)
            if now - os.path.getmtime(full) > PREVIEW_TTL_SECONDS:
                os.remove(full)
    except OSError:
        pass


def _stash_preview(payload):
    """Write the parsed rows aside and return the token that retrieves them."""
    _purge_stale_previews()
    token = secrets.token_urlsafe(16)
    with open(_preview_path(token), 'w', encoding='utf-8') as fh:
        json.dump(payload, fh)
    return token


def _take_preview(token):
    """Read and consume a staged preview. Returns None if it's gone."""
    path = _preview_path(token)
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return data


def _student_lookup():
    """Caseload-scoped id/name -> Student.id maps for matching import rows."""
    rows = Student.query.filter_by(
        assigned_counselor_id=current_user.id
    ).with_entities(Student.id, Student.student_id_number,
                    Student.last_name, Student.first_name).all()
    by_sid, by_name = {}, {}
    for sid, num, last, first in rows:
        if num:
            by_sid[str(num).strip().lower()] = sid
        if last and first:
            by_name[f'{last.strip().lower()}, {first.strip().lower()}'] = sid
    return by_sid, by_name


def _match_student(row, by_sid, by_name):
    """Resolve a parsed row to a caseload student id, or None.

    Perm ID first (exact and unambiguous), name second. Never creates a
    student — an unmatched row is reported, not invented, because silently
    attaching a schedule to the wrong student is worse than failing loudly.
    """
    ref = (row.student_ref or '').strip().lower()
    if ref and ref in by_sid:
        return by_sid[ref]
    name = (row.student_name or '').strip().lower()
    if name:
        if name in by_name:
            return by_name[name]
        # Tolerate "Last, First Middle" by trying the first two components.
        parts = [p.strip() for p in name.split(',')]
        if len(parts) == 2:
            key = f'{parts[0]}, {parts[1].split()[0]}' if parts[1] else ''
            if key in by_name:
                return by_name[key]
    return None


def _credit_lookup(course_numbers):
    """course_number -> credits from the Course catalog, where known."""
    if not course_numbers:
        return {}
    rows = Course.query.filter(
        Course.course_number.in_(list(course_numbers))
    ).with_entities(Course.course_number, Course.credits).all()
    return {str(n).strip(): c for n, c in rows if c is not None}


@data_import_bp.route('/schedules', methods=['GET', 'POST'])
@login_required
def schedules_upload():
    """Step 1 — accept file(s), parse, and show a preview."""
    if request.method == 'GET':
        return render_template('data_import/schedules_upload.html')

    files = [f for f in request.files.getlist('files') if f and f.filename]
    if not files:
        flash('Please choose at least one file.', 'danger')
        return redirect(url_for('data_import.schedules_upload'))

    parsed, parse_errors = [], []
    for f in files:
        try:
            parsed.extend(parse_schedule_file(f, f.filename))
        except Exception as e:
            parse_errors.append(f'{f.filename}: {e}')

    if parse_errors:
        for msg in parse_errors:
            flash(msg, 'danger')
    if not parsed:
        flash('No schedule rows were found in that file.', 'warning')
        return redirect(url_for('data_import.schedules_upload'))

    by_sid, by_name = _student_lookup()
    credits_by_course = _credit_lookup({p.course_number for p in parsed})

    matched, unmatched = [], defaultdict(list)
    for p in parsed:
        student_id = _match_student(p, by_sid, by_name)
        rec = {
            'student_id': student_id,
            'student_ref': p.student_ref,
            'student_name': p.student_name,
            'school_year': p.school_year,
            'term': p.term,
            'period': p.period,
            'course_number': p.course_number,
            'course_title': p.course_title,
            'section_id': p.section_id,
            'teacher_name': p.teacher_name,
            'room': p.room,
            'start_date': p.start_date.isoformat() if p.start_date else None,
            'is_advisory': p.is_advisory,
            'is_non_class': p.is_non_class,
            'source': p.source,
            'credits': credits_by_course.get(p.course_number),
        }
        if student_id:
            matched.append(rec)
        else:
            unmatched[p.student_ref or p.student_name or '(no identifier)'].append(rec)

    # A PDF of a single student carries the identity in the page header; if it
    # was redacted or unreadable there is nothing to match on, and the
    # counselor picks the student by hand on the preview.
    needs_student_pick = bool(unmatched) and len(files) == 1 and all(
        not r['student_ref'] and not r['student_name']
        for rows in unmatched.values() for r in rows)

    session[PREVIEW_KEY] = _stash_preview({
        'matched': matched,
        'unmatched': [r for rows in unmatched.values() for r in rows],
    })

    names = {m['student_id'] for m in matched}
    students = {s.id: s for s in Student.query.filter(Student.id.in_(names)).all()} if names else {}
    missing_credits = sorted({m['course_number'] for m in matched
                              if m['credits'] is None and not m['is_non_class']
                              and not m['is_advisory']})

    # Everything this upload would actually write. When the identity was
    # unreadable the counselor assigns the file to a student right here, so
    # those rows import too — summarising only `matched` would show nothing at
    # all for a redacted single-student file that is about to import fine.
    preview_rows = matched + (
        [r for rows in unmatched.values() for r in rows] if needs_student_pick else [])

    # Who this upload would add to the staff directory, shown before committing
    # so a name that is misspelled in the SIS is caught here rather than
    # becoming a duplicate teacher nobody notices.
    staff_preview = summarize_staff(
        derive_staff_from_schedule(preview_rows),
        [s.name for s in Staff.query.with_entities(Staff.name).all()])

    return render_template(
        'data_import/schedules_preview.html',
        matched=matched, unmatched=dict(unmatched), students=students,
        missing_credits=missing_credits, staff_preview=staff_preview,
        preview_rows=preview_rows,
        needs_student_pick=needs_student_pick,
        caseload=Student.query.filter_by(
            assigned_counselor_id=current_user.id, status='active'
        ).order_by(Student.last_name).all() if needs_student_pick else [],
        school_years=sorted({m['school_year'] for m in matched if m['school_year']}),
    )


@data_import_bp.route('/schedules/confirm', methods=['POST'])
@login_required
def schedules_confirm():
    """Step 2 — commit the previewed rows."""
    data = _take_preview(session.pop(PREVIEW_KEY, None))
    if not data:
        flash('That preview is no longer available. Please upload the file again.',
              'warning')
        return redirect(url_for('data_import.schedules_upload'))
    rows = data.get('matched', [])

    # The counselor may assign a single-student file by hand when the printout
    # had no readable identity.
    manual_student = request.form.get('manual_student_id', '').strip()
    if manual_student.isdigit():
        target = Student.query.filter_by(
            id=int(manual_student), assigned_counselor_id=current_user.id).first()
        if target:
            for r in data.get('unmatched', []):
                r['student_id'] = target.id
                rows.append(r)

    if not rows:
        flash('Nothing to import.', 'warning')
        return redirect(url_for('data_import.schedules_upload'))

    default_credits = request.form.get('default_credits', '').strip()
    try:
        default_credits = float(default_credits) if default_credits else None
    except ValueError:
        default_credits = None

    # Irreversible bulk replace below — take a snapshot first, same as rollover.
    snap = snapshot_database('pre_schedule_import')
    if snap:
        log_action('backup', 'database', details='Pre-schedule-import snapshot')

    # Replace, don't append: a re-import means the schedule changed.
    pairs = {(r['student_id'], r['school_year']) for r in rows}
    replaced = 0
    for student_id, year in pairs:
        replaced += ScheduleEntry.query.filter_by(
            student_id=student_id, school_year=year).delete(synchronize_session=False)

    seeded_courses = 0
    known = {c.course_number for c in Course.query.with_entities(
        Course.course_number).all() if c.course_number}

    added = 0
    for r in rows:
        credits = r.get('credits')
        if credits is None and not r['is_non_class'] and not r['is_advisory']:
            credits = default_credits

        db.session.add(ScheduleEntry(
            student_id=r['student_id'],
            school_year=r['school_year'],
            term=r['term'] or 'YR',
            period=r['period'],
            course_number=r['course_number'],
            course_title=r['course_title'],
            section_id=r['section_id'],
            teacher_name=r['teacher_name'],
            room=r['room'],
            start_date=_parse_iso(r.get('start_date')),
            credits=credits,
            is_advisory=r['is_advisory'],
            is_non_class=r['is_non_class'],
            source=r['source'],
            imported_by_id=current_user.id,
        ))
        added += 1

        # Seed the course catalog from what's actually being taught, so credits
        # resolve automatically next time instead of being asked for again.
        num = r['course_number']
        if num and num not in known and not r['is_non_class']:
            db.session.add(Course(
                course_number=num,
                title=r['course_title'],
                credits=credits,
                instructor=r['teacher_name'],
                room=r['room'],
                school_year=r['school_year'],
                is_active=True,
            ))
            known.add(num)
            seeded_courses += 1

    # Fill the staff directory from the same upload. Without this it stays empty
    # until the first grades land, which is exactly the stretch of the year a
    # counselor most needs to know who teaches what. Derived fields only ever
    # fill blanks, so anything the counselor typed survives a re-import.
    dept_by_course = {
        c.course_number: c.department_name
        for c in Course.query.with_entities(
            Course.course_number, Course.department_name).all()
        if c.course_number and c.department_name
    }
    derived_staff = derive_staff_from_schedule(rows, dept_by_course)
    existing_staff = {}
    if derived_staff:
        existing_staff = {
            s.name.strip().lower(): s for s in
            Staff.query.filter(db.func.lower(Staff.name).in_(
                list(derived_staff.keys()))).all()
        }
    staff_added, staff_enriched = apply_staff_records(
        derived_staff, existing_staff,
        lambda **fields: db.session.add(Staff(**fields)))

    db.session.add(ImportLog(
        user_id=current_user.id,
        import_type='schedules',
        school_year=next((r['school_year'] for r in rows if r['school_year']), None),
        records_added=added,
        records_skipped=len(data.get('unmatched', [])) if not manual_student else 0,
    ))
    db.session.commit()
    log_action('import', 'schedule',
               details=f'Imported {added} schedule rows for {len(pairs)} student-year(s); '
                       f'replaced {replaced}; seeded {seeded_courses} course(s); '
                       f'staff {staff_added} added, {staff_enriched} updated')

    msg = f'Imported {added} schedule rows for {len({p[0] for p in pairs})} student(s).'
    if seeded_courses:
        msg += f' Added {seeded_courses} new course(s) to the catalog.'
    if staff_added or staff_enriched:
        bits = []
        if staff_added:
            bits.append(f'added {staff_added}')
        if staff_enriched:
            bits.append(f'filled in details for {staff_enriched}')
        msg += f' Staff directory: {" and ".join(bits)}.'
    flash(msg, 'success')
    return redirect(url_for('data_import.index'))


def _parse_iso(value):
    if not value:
        return None
    from datetime import date as _date
    try:
        return _date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


@data_import_bp.route('/course-catalog/seed', methods=['POST'])
@login_required
def seed_course_catalog():
    """Load the district catalog shipped with the app into the Course table.

    It already sits in app/static/course_catalog/index.html as display data for
    the Catalog Wiki — 126 courses with codes, credits, a-g and prerequisite
    prose — but nothing reads it. Importing gives schedule imports their credit
    values and gives the schedule checker prerequisites it can actually
    evaluate. Existing rows are never clobbered: a credit value you corrected
    by hand outranks the shipped file.
    """
    from app.models.course import Course
    from app.utils.catalog_seed import seed_courses

    try:
        created, updated, skipped = seed_courses(db, Course)
    except Exception as e:
        flash(f'Could not read the course catalog: {e}', 'danger')
        return redirect(url_for('data_import.index'))

    log_action('import', 'course',
               details=f'Seeded catalog: {created} created, {updated} updated')
    flash(f'Course catalog loaded — {created} new course(s), {updated} updated, '
          f'{skipped} already up to date. Schedule imports will now fill in '
          'credits automatically and prerequisites can be checked.', 'success')
    return redirect(url_for('data_import.index'))
