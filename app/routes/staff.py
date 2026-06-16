"""Staff directory + per-staff detail/edit.

Staff records are auto-created from the Staff Name column in grade imports;
this module joins them with the grade data to show each teacher's classes,
which of the counselor's students are in those classes, and any contact info
or notes the counselor has added.
"""
from collections import defaultdict
from datetime import date as _date
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, abort)
from flask_login import login_required, current_user
from app import db
from app.models.staff import Staff
from app.models.student import Student
from app.models.grade import GradeRecord
from app.models.communication import CommunicationLog
from app.utils.audit import log_action
from app.utils.helpers import parse_date
from app.utils.roles import caseload_student_or_404

staff_bp = Blueprint('staff', __name__)

_DF = {'F', 'NP', 'D+', 'D', 'D-'}


def _grades_for_caseload(student_ids):
    """Final grades for the counselor's caseload with a teacher recorded."""
    if not student_ids:
        return []
    return GradeRecord.query.filter(
        GradeRecord.student_id.in_(student_ids),
        GradeRecord.teacher.isnot(None),
        GradeRecord.teacher != '',
        GradeRecord.grade_type == 'final',
    ).all()


@staff_bp.route('/')
@login_required
def index():
    """Roster: persistent staff rows joined with grade-derived stats."""
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active').all()
    student_ids = [s.id for s in students]
    grades = _grades_for_caseload(student_ids)

    years = sorted({g.school_year for g in grades if g.school_year}, reverse=True)
    year = request.args.get('year') or (years[0] if years else '')

    # teacher (lowercased) -> aggregates for the selected year, plus the
    # display name as it first appeared in the grade data (so a teacher not
    # yet in the Staff table still renders with proper casing).
    by_name = defaultdict(lambda: {
        'display': '',
        'classes': defaultdict(lambda: {'students': set(), 'df': 0, 'total': 0,
                                        'subjects': set()}),
    })
    for g in grades:
        if year and g.school_year != year:
            continue
        raw = (g.teacher or '').strip()
        key = raw.lower()
        if not by_name[key]['display']:
            by_name[key]['display'] = raw
        cell = by_name[key]['classes'][(g.course_name or 'Unknown', g.period)]
        cell['students'].add(g.student_id)
        cell['total'] += 1
        if g.subject_area:
            cell['subjects'].add(g.subject_area)
        if (g.letter_grade or '').strip() in _DF:
            cell['df'] += 1

    rows = []
    # Show every persistent Staff record, plus any teacher seen this year that
    # somehow lacks one (shouldn't happen after the import auto-upsert, but
    # protects against legacy data).
    all_staff = Staff.query.order_by(Staff.name).all()
    staff_by_lower = {s.name.lower(): s for s in all_staff}
    seen_keys = set()
    for s in all_staff:
        seen_keys.add(s.name.lower())
        classes = by_name.get(s.name.lower(), {}).get('classes', {})
        rows.append(_build_row(s, classes))
    for key, agg in by_name.items():
        if key and key not in seen_keys:
            placeholder = Staff(id=None, name=agg['display'] or key, title='Teacher')
            rows.append(_build_row(placeholder, agg['classes']))

    # Sort: people you actually have students with first (biggest student count),
    # then alphabetical for the rest.
    rows.sort(key=lambda r: (
        0 if r['student_count'] else 1,
        -r['student_count'],
        r['name'].lower(),
    ))

    return render_template('staff/index.html', rows=rows, year=year, years=years,
                           has_data=bool(rows))


def _build_row(staff, classes):
    """Shape a staff row for the directory."""
    class_list, all_students, total_df, total_grades, subjects = [], set(), 0, 0, set()
    for (course, period), c in classes.items():
        class_list.append({
            'course': course, 'period': period,
            'students': len(c['students']), 'df': c['df'], 'total': c['total'],
            'rate': round(c['df'] / c['total'] * 100, 1) if c['total'] else 0,
        })
        all_students |= c['students']
        total_df += c['df']
        total_grades += c['total']
        subjects |= c['subjects']
    class_list.sort(key=lambda r: (r['period'] if r['period'] is not None else 99, r['course']))
    derived_dept = next(iter(subjects), '') if len(subjects) == 1 else (
        '/'.join(sorted(subjects)) if subjects else '')
    return {
        'id': staff.id,
        'name': staff.name,
        'title': staff.title or '',
        'email': staff.email or '',
        'phone': staff.phone or '',
        'room': staff.room or '',
        'department': (staff.department or '').strip() or derived_dept,
        'notes': staff.notes or '',
        'classes': class_list,
        'class_count': len(class_list),
        'student_count': len(all_students),
        'df': total_df,
        'rate': round(total_df / total_grades * 100, 1) if total_grades else 0,
        'has_record': staff.id is not None,
    }


@staff_bp.route('/create', methods=['POST'])
@login_required
def create_from_name():
    """Promote a grade-derived (placeholder) teacher into a real Staff record.

    Idempotent: if a Staff row with this name already exists (case-insensitive),
    we land on that one instead of creating a duplicate. Either way, redirect
    to the detail page so the counselor can fill in email/notes immediately.
    """
    name = (request.form.get('name') or '').strip()
    if not name:
        flash('Teacher name is required.', 'error')
        return redirect(url_for('staff.index'))
    existing = Staff.query.filter(db.func.lower(Staff.name) == name.lower()).first()
    if existing:
        return redirect(url_for('staff.detail', staff_id=existing.id))
    staff = Staff(name=name, title='Teacher')
    db.session.add(staff)
    db.session.commit()
    log_action('create', 'staff', staff.id, f'Created staff record: {name}')
    flash(f'Created staff record for {name}. Add their contact info here.', 'success')
    return redirect(url_for('staff.detail', staff_id=staff.id))


@staff_bp.route('/<int:staff_id>')
@login_required
def detail(staff_id):
    """Profile + classes + which of YOUR students are in each."""
    staff = Staff.query.get_or_404(staff_id)
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active').all()
    student_ids = [s.id for s in students]
    name_by_id = {s.id: s for s in students}

    grades = []
    if student_ids:
        grades = GradeRecord.query.filter(
            GradeRecord.student_id.in_(student_ids),
            db.func.lower(GradeRecord.teacher) == staff.name.lower(),
            GradeRecord.grade_type == 'final',
        ).all()

    years = sorted({g.school_year for g in grades if g.school_year}, reverse=True)
    year = request.args.get('year') or (years[0] if years else '')

    # (course, period) -> list of (student, latest grade)
    classes = defaultdict(lambda: {'rows': [], 'subjects': set()})
    # For "latest grade per student per class," pick the highest quarter we have
    # for the selected year (final grades only — already filtered above).
    by_student_class = {}
    for g in grades:
        if year and g.school_year != year:
            continue
        key = (g.course_name or 'Unknown', g.period, g.student_id)
        prev = by_student_class.get(key)
        if not prev or (g.quarter or 0) > (prev.quarter or 0):
            by_student_class[key] = g

    for (course, period, sid), g in by_student_class.items():
        s = name_by_id.get(sid)
        if not s:
            continue
        classes[(course, period)]['rows'].append({
            'id': sid,
            'name': f'{s.first_name} {s.last_name}',
            'grade_level': s.grade_level,
            'letter': (g.letter_grade or '').strip(),
            'is_df': (g.letter_grade or '').strip() in _DF,
            'quarter': g.quarter,
        })
        if g.subject_area:
            classes[(course, period)]['subjects'].add(g.subject_area)

    class_blocks = []
    subjects_all = set()
    for (course, period), pack in classes.items():
        pack['rows'].sort(key=lambda r: (not r['is_df'], r['name'].lower()))
        df = sum(1 for r in pack['rows'] if r['is_df'])
        class_blocks.append({
            'course': course, 'period': period,
            'rows': pack['rows'], 'df': df,
            'students': len(pack['rows']),
            'subjects': pack['subjects'],
        })
        subjects_all |= pack['subjects']
    class_blocks.sort(key=lambda b: (b['period'] if b['period'] is not None else 99, b['course']))

    derived_dept = next(iter(subjects_all), '') if len(subjects_all) == 1 else (
        '/'.join(sorted(subjects_all)) if subjects_all else '')

    # Communications + open follow-ups with this staff member (most recent first)
    comms = CommunicationLog.query.filter_by(
        staff_id=staff.id, counselor_id=current_user.id
    ).order_by(CommunicationLog.contact_date.desc(),
               CommunicationLog.created_at.desc()).limit(50).all()
    open_followups = [c for c in comms if c.follow_up_needed and not c.follow_up_completed]

    log_action('view', 'staff', staff.id)
    return render_template('staff/detail.html', staff=staff, classes=class_blocks,
                           year=year, years=years, derived_dept=derived_dept,
                           titles=Staff.TITLES,
                           comms=comms, open_followups=open_followups,
                           contact_types=CommunicationLog.CONTACT_TYPES,
                           today=_date.today())


@staff_bp.route('/<int:staff_id>/edit', methods=['POST'])
@login_required
def update(staff_id):
    """Save the editable contact + classification fields."""
    staff = Staff.query.get_or_404(staff_id)
    new_name = request.form.get('name', '').strip()
    if not new_name:
        flash('Name is required.', 'error')
        return redirect(url_for('staff.detail', staff_id=staff.id))

    # If the name changed, rename matching GradeRecord.teacher entries so the
    # directory and Insights chart keep pointing at this record. Block a rename
    # that would collide with another existing staff record (force a manual fix).
    if new_name.lower() != staff.name.lower():
        clash = Staff.query.filter(
            db.func.lower(Staff.name) == new_name.lower(),
            Staff.id != staff.id).first()
        if clash:
            flash(f'Another staff record already uses the name "{new_name}".', 'error')
            return redirect(url_for('staff.detail', staff_id=staff.id))
        GradeRecord.query.filter(
            db.func.lower(GradeRecord.teacher) == staff.name.lower()
        ).update({'teacher': new_name}, synchronize_session=False)

    staff.name = new_name
    staff.email = request.form.get('email', '').strip() or None
    staff.phone = request.form.get('phone', '').strip() or None
    staff.room = request.form.get('room', '').strip() or None
    staff.title = request.form.get('title', '').strip() or None
    staff.department = request.form.get('department', '').strip() or None
    staff.notes = request.form.get('notes', '').strip() or None
    db.session.commit()
    log_action('update', 'staff', staff.id, f'Edited staff: {staff.name}')
    flash(f'Saved changes to {staff.name}.', 'success')
    return redirect(url_for('staff.detail', staff_id=staff.id))


@staff_bp.route('/<int:staff_id>/log-communication', methods=['POST'])
@login_required
def log_communication(staff_id):
    """Log an email/call/meeting from this staff member, optionally with a
    follow-up reminder. The defaults (incoming, email) match the common case
    of a teacher emailing the counselor."""
    staff = Staff.query.get_or_404(staff_id)

    contact_type = (request.form.get('contact_type') or 'email').strip()
    direction = (request.form.get('direction') or 'incoming').strip()
    contact_date = parse_date(request.form.get('contact_date')) or _date.today()
    subject = (request.form.get('subject') or '').strip()
    summary = (request.form.get('summary') or '').strip()

    follow_up_needed = 'follow_up_needed' in request.form
    follow_up_date = parse_date(request.form.get('follow_up_date'))
    follow_up_notes = (request.form.get('follow_up_notes') or '').strip()
    # Common-case safeguard: a follow-up checked without a date defaults to one
    # week out so the reminder still surfaces somewhere.
    if follow_up_needed and not follow_up_date:
        from datetime import timedelta
        follow_up_date = _date.today() + timedelta(days=7)

    subject = caseload_student_or_404(request.form.get('student_id'), allow_none=True)
    student_id = subject.id if subject else None

    log = CommunicationLog(
        staff_id=staff.id,
        student_id=student_id,
        counselor_id=current_user.id,
        contact_date=contact_date,
        contact_type=contact_type,
        direction=direction,
        contact_person=staff.name,
        contact_role='teacher' if (staff.title or '').lower() == 'teacher' else 'other',
        contact_email=staff.email or '',
        contact_phone=staff.phone or '',
        subject=subject,
        summary=summary,
        follow_up_needed=follow_up_needed,
        follow_up_date=follow_up_date,
        follow_up_notes=follow_up_notes,
    )
    db.session.add(log)
    db.session.commit()
    log_action('create', 'communication', log.id,
               f'Logged {contact_type} with {staff.name}'
               + (f' · follow-up {follow_up_date.isoformat()}' if follow_up_date else ''))
    flash(f'Logged {dict(CommunicationLog.CONTACT_TYPES).get(contact_type, contact_type)} from {staff.name}.', 'success')
    return redirect(url_for('staff.detail', staff_id=staff.id) + '#comms')


@staff_bp.route('/communications/<int:comm_id>/complete', methods=['POST'])
@login_required
def complete_followup(comm_id):
    """Mark a staff communication's follow-up complete (the dashboard widget
    and the staff detail page both POST here)."""
    log = CommunicationLog.query.filter_by(
        id=comm_id, counselor_id=current_user.id).first_or_404()
    log.follow_up_completed = True
    db.session.commit()
    log_action('update', 'communication', log.id, 'Marked follow-up complete')
    if request.is_json:
        from flask import jsonify
        return jsonify({'ok': True})
    return redirect(request.referrer or url_for('staff.detail', staff_id=log.staff_id or 0))
