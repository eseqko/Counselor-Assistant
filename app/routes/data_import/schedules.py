"""Import student class schedules from a Synergy export or a printed PDF.

Flow mirrors the other importers: upload -> PREVIEW -> confirm -> commit.
The preview matters more here than elsewhere, because the PDF path reads a
printout by column position and the counselor is the one who can tell at a
glance whether it read correctly.

Both file types funnel through app/utils/schedule_parser, which normalizes them
to the same row shape, so everything below is format-agnostic.
"""
import json
from collections import defaultdict

from flask import (render_template, request, redirect, url_for, flash, session)
from flask_login import login_required, current_user

from app import db
from app.models.course import Course
from app.models.import_log import ImportLog
from app.models.schedule import ScheduleEntry
from app.models.student import Student
from app.routes.data_import import data_import_bp
from app.utils.audit import log_action
from app.utils.db_snapshot import snapshot_database
from app.utils.schedule_parser import parse_schedule_file

# Preview payload lives in the session between the two requests; a caseload of
# ~200 students is a few hundred KB of JSON, well within a cookie-backed
# session's practical limit only if we keep it lean, so we store the parsed
# rows rather than the raw file.
PREVIEW_KEY = 'schedule_preview'


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

    session[PREVIEW_KEY] = json.dumps({'matched': matched,
                                       'unmatched': [r for rows in unmatched.values()
                                                     for r in rows]})

    names = {m['student_id'] for m in matched}
    students = {s.id: s for s in Student.query.filter(Student.id.in_(names)).all()} if names else {}
    missing_credits = sorted({m['course_number'] for m in matched
                              if m['credits'] is None and not m['is_non_class']
                              and not m['is_advisory']})

    return render_template(
        'data_import/schedules_preview.html',
        matched=matched, unmatched=dict(unmatched), students=students,
        missing_credits=missing_credits,
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
    payload = session.pop(PREVIEW_KEY, None)
    if not payload:
        flash('That preview expired. Please upload the file again.', 'warning')
        return redirect(url_for('data_import.schedules_upload'))

    data = json.loads(payload)
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
                       f'replaced {replaced}; seeded {seeded_courses} course(s)')

    msg = f'Imported {added} schedule rows for {len({p[0] for p in pairs})} student(s).'
    if seeded_courses:
        msg += f' Added {seeded_courses} new course(s) to the catalog.'
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
