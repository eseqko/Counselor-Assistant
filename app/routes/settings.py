import json
import os
import re
import shutil
from datetime import datetime, date, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, Response
from flask_login import login_required, current_user
from flask import jsonify
from app import db, csrf
from app.models.user import AuditLog
from app.models.student import Student, Tag
from app.models.note import Note
from app.models.service_record import ServiceRecord
from app.models.transcript import TranscriptRecord
from app.models.course import Department, Course, GraduationRequirement
from app.utils.audit import log_action
from app.utils.helpers import current_school_year
from config import Config

settings_bp = Blueprint('settings', __name__)


def _cleanup_duplicate_notes():
    """Remove duplicate notes, keeping the oldest (lowest id) for each unique combination."""
    from sqlalchemy import func

    # Find groups with duplicates: same student + note_type + title + content
    dupes = db.session.query(
        Note.student_id, Note.note_type, Note.title, Note.content,
        func.min(Note.id).label('keep_id'),
        func.count(Note.id).label('cnt')
    ).group_by(
        Note.student_id, Note.note_type, Note.title, Note.content
    ).having(func.count(Note.id) > 1).all()

    total_removed = 0
    for row in dupes:
        # Delete all but the one with lowest id
        extras = Note.query.filter(
            Note.student_id == row.student_id,
            Note.note_type == row.note_type,
            Note.title == row.title,
            Note.content == row.content,
            Note.id != row.keep_id
        ).all()
        for note in extras:
            db.session.delete(note)
        total_removed += len(extras)

    if total_removed:
        db.session.commit()
    return total_removed


@settings_bp.route('/')
@login_required
def index():
    return render_template('settings/index.html')


@settings_bp.route('/api/theme', methods=['POST'])
@csrf.exempt
@login_required
def update_theme():
    """Save theme preference (called from JS)."""
    data = request.get_json(silent=True) or {}
    theme = data.get('theme', 'light')
    if theme not in ('light', 'dark', 'school', 'focus', 'auto', 'fiesta', 'glass'):
        theme = 'light'
    current_user.theme_preference = theme
    current_user.reduced_motion = bool(data.get('reduced_motion', False))
    db.session.commit()
    return jsonify({'ok': True, 'theme': theme})


@settings_bp.route('/api/theme')
@login_required
def get_theme():
    """Return current theme preference."""
    return jsonify({
        'theme': current_user.theme_preference or 'light',
        'reduced_motion': current_user.reduced_motion or False
    })


@settings_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_user.display_name = request.form.get('display_name', current_user.display_name)
        current_user.school_name = request.form.get('school_name', '')
        synergy_url = request.form.get('synergy_base_url', '').strip()
        if synergy_url and not synergy_url.startswith(('http://', 'https://')):
            synergy_url = 'https://' + synergy_url
        current_user.synergy_base_url = synergy_url
        db.session.commit()
        flash('Profile updated.', 'success')
        return redirect(url_for('settings.profile'))

    return render_template('settings/profile.html')


@settings_bp.route('/audit-log')
@login_required
def audit_log():
    page = request.args.get('page', 1, type=int)
    query = AuditLog.query
    # Counselors see only their own trail; admins see the whole school's.
    if current_user.role != 'admin':
        query = query.filter_by(user_id=current_user.id)
    logs = query.order_by(AuditLog.timestamp.desc()).paginate(
        page=page, per_page=50, error_out=False)
    return render_template('settings/audit_log.html', logs=logs)


@settings_bp.route('/backup', methods=['POST'])
@login_required
def backup():
    """Create a local backup of the database."""
    backup_dir = Config.BACKUP_DIR
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(backup_dir, f'counselor_backup_{timestamp}.db')
    db_path = os.path.join(Config.DATA_DIR if hasattr(Config, 'DATA_DIR') else 'data', 'counselor.db')

    try:
        shutil.copy2(db_path, backup_path)
        log_action('backup', 'database', details=f'Backup created: {backup_path}')
        flash('Backup created successfully.', 'success')
    except Exception:
        flash('Backup failed. Please check disk space and try again.', 'danger')

    return redirect(url_for('settings.index'))


@settings_bp.route('/export-backup')
@login_required
def export_backup():
    """Download the latest backup."""
    backup_dir = Config.BACKUP_DIR
    if not os.path.exists(backup_dir):
        flash('No backups found.', 'warning')
        return redirect(url_for('settings.index'))

    backups = sorted(
        [f for f in os.listdir(backup_dir) if f.endswith('.db')],
        reverse=True
    )
    if not backups:
        flash('No backups found.', 'warning')
        return redirect(url_for('settings.index'))

    backup_path = os.path.join(backup_dir, backups[0])
    if not os.path.abspath(backup_path).startswith(os.path.abspath(backup_dir)):
        flash('Invalid backup file.', 'danger')
        return redirect(url_for('settings.index'))
    log_action('export', 'database', details='Downloaded backup')
    return send_file(backup_path, as_attachment=True)


def _serialize_date(val):
    """Convert date/datetime to ISO string for JSON."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, date):
        return val.isoformat()
    return str(val)


def _parse_date(val):
    """Parse ISO date string back to date object."""
    if not val:
        return None
    try:
        if 'T' in val:
            return datetime.fromisoformat(val)
        return date.fromisoformat(val)
    except (ValueError, TypeError):
        return None


# Row → dict converters used by export_data. Keep field names stable;
# import_data reads them by exact key.

def _student_to_dict(s):
    return {
        'student_id_number': s.student_id_number,
        'first_name': s.first_name,
        'last_name': s.last_name,
        'grade_level': s.grade_level,
        'date_of_birth': _serialize_date(s.date_of_birth),
        'gender': s.gender,
        'ethnicity': s.ethnicity,
        'email': s.email,
        'phone': s.phone,
        'parent_guardian_name': s.parent_guardian_name,
        'parent_guardian_phone': s.parent_guardian_phone,
        'parent_guardian_email': s.parent_guardian_email,
        'address': s.address,
        'homeroom': s.homeroom,
        'status': s.status,
        'enrollment_date': _serialize_date(s.enrollment_date),
        'iep_status': s.iep_status,
        'section_504': s.section_504,
        'el_status': s.el_status,
        'el_level': s.el_level,
        'special_programs': s.special_programs,
        'notes_text': s.notes_text,
        'tags': [t.name for t in s.tags],
    }


def _note_to_dict(n):
    return {
        'student_id_number': n.student.student_id_number if n.student else None,
        'note_type': n.note_type,
        'title': n.title,
        'content': n.content,
        'session_date': _serialize_date(n.session_date),
        'duration_minutes': n.duration_minutes,
        'asca_domain': n.asca_domain,
        'asca_standard': n.asca_standard,
        'topic_category': n.topic_category,
        'delivery_method': n.delivery_method,
        'follow_up_needed': n.follow_up_needed,
        'follow_up_date': _serialize_date(n.follow_up_date),
        'follow_up_notes': n.follow_up_notes,
        'follow_up_completed': n.follow_up_completed,
        'follow_up_completed_date': _serialize_date(n.follow_up_completed_date),
        'is_confidential': n.is_confidential,
        'restricted_access': n.restricted_access,
        'created_at': _serialize_date(n.created_at),
    }


def _service_record_to_dict(sr):
    return {
        'student_id_number': sr.student.student_id_number if sr.student else None,
        'date': _serialize_date(sr.date),
        'service_type': sr.service_type,
        'topic': sr.topic,
        'description': sr.description,
        'duration_minutes': sr.duration_minutes,
        'asca_domain': sr.asca_domain,
        'asca_standard': sr.asca_standard,
        'delivery_method': sr.delivery_method,
        'setting': sr.setting,
        'outcome': sr.outcome,
        'follow_up_required': sr.follow_up_required,
        'follow_up_date': _serialize_date(sr.follow_up_date),
        'referral_made': sr.referral_made,
        'referral_to': sr.referral_to,
        'created_at': _serialize_date(sr.created_at),
    }


def _transcript_to_dict(tr):
    return {
        'student_id_number': tr.student.student_id_number if tr.student else None,
        'quarter': tr.quarter,
        'total_completed': tr.total_completed,
        'total_wip': tr.total_wip,
        'total_needed': tr.total_needed,
        'risk_level': tr.risk_level,
        'ag_status': tr.ag_status,
        'ag_areas_met': tr.ag_areas_met,
        'ag_areas_deficient': tr.ag_areas_deficient,
        'cte_completed': tr.cte_completed,
        'cte_level': tr.cte_level,
        'cte_is_completer': tr.cte_is_completer,
        'credits_json': tr.credits_json,
        'ag_json': tr.ag_json,
        'import_date': _serialize_date(tr.import_date),
    }


def _department_to_dict(d):
    return {
        'name': d.name,
        'description': d.description,
        'head': d.head,
        'color': d.color,
        'sort_order': d.sort_order,
    }


def _course_to_dict(c):
    return {
        'department_name': c.department.name if c.department else None,
        'course_number': c.course_number,
        'title': c.title,
        'description': c.description,
        'credits': c.credits,
        'grade_levels': c.grade_levels,
        'prerequisites': c.prerequisites,
        'corequisites': c.corequisites,
        'course_type': c.course_type,
        'subject_area': c.subject_area,
        'is_weighted': c.is_weighted,
        'weight': c.weight,
        'meets_requirement': c.meets_requirement,
        'ncaa_approved': c.ncaa_approved,
        'max_enrollment': c.max_enrollment,
        'semesters': c.semesters,
        'instructor': c.instructor,
        'room': c.room,
        'detailed_description': c.detailed_description,
        'resources': c.resources,
        'notes': c.notes,
        'is_active': c.is_active,
        'school_year': c.school_year,
    }


def _grad_req_to_dict(gr):
    return {
        'name': gr.name,
        'credits_required': gr.credits_required,
        'description': gr.description,
        'qualifying_courses': gr.qualifying_courses,
        'sort_order': gr.sort_order,
    }


@settings_bp.route('/export-data')
@login_required
def export_data():
    """Export caseload and course catalog data as a portable JSON file.

    Streams the response so the file starts downloading immediately and
    we never hold the full output as a single string in memory. Per-table
    queries use eager loads to avoid N+1 lookups against Student.
    """
    from flask import stream_with_context
    from sqlalchemy.orm import joinedload, selectinload

    school = (current_user.school_name or 'export').replace(' ', '_')
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    filename = f'counselor_data_{school}_{timestamp}.json'

    log_action('export', 'data_transfer', details=f'Exported portable data file: {filename}')

    # Capture user fields up front; current_user proxies the request context
    # and we want stable values to use inside the generator.
    exported_by = current_user.display_name or current_user.username
    school_config_raw = current_user.school_config_json
    owner_id = current_user.id  # scope the export to this counselor's own data

    def emit_array(name, rows, to_dict, leading_comma=True):
        """Yield a JSON array element 'name': [ ... ] with rows streamed in."""
        prefix = ',\n' if leading_comma else '\n'
        yield f'{prefix}  "{name}": ['
        first = True
        for row in rows:
            sep = '\n    ' if first else ',\n    '
            yield sep + json.dumps(to_dict(row), ensure_ascii=False)
            first = False
        yield ('\n  ]' if not first else ']')

    def generate():
        yield '{\n'
        yield f'  "export_version": 1,\n'
        yield f'  "exported_at": {json.dumps(datetime.now(timezone.utc).isoformat())},\n'
        yield f'  "exported_by": {json.dumps(exported_by)}'

        # Optional school config block
        if school_config_raw:
            try:
                cfg = json.loads(school_config_raw)
                yield ',\n  "school_config": ' + json.dumps(cfg, ensure_ascii=False)
            except (json.JSONDecodeError, TypeError):
                pass

        yield from emit_array('tags', Tag.query.all(),
                              lambda t: {'name': t.name, 'color': t.color})

        # Scope the export to THIS counselor's own data — never serialize another
        # counselor's students/notes/records, or shadow students (synthetic rows
        # from whole-school grade/attendance files), into a portable file. The
        # catalog blocks below (tags, departments, courses, grad requirements)
        # are shared config, not student PII.
        my_student_ids = [row[0] for row in Student.query.filter_by(
            assigned_counselor_id=owner_id).with_entities(Student.id).all()]

        students = Student.query.filter_by(
            assigned_counselor_id=owner_id).options(
            selectinload(Student.tags)).all()
        yield from emit_array('students', students, _student_to_dict)

        notes = Note.query.filter_by(author_id=owner_id).options(
            joinedload(Note.student)).all()
        yield from emit_array('notes', notes, _note_to_dict)

        services = ServiceRecord.query.filter_by(counselor_id=owner_id).options(
            joinedload(ServiceRecord.student)).all()
        yield from emit_array('service_records', services, _service_record_to_dict)

        transcripts = (TranscriptRecord.query.filter(
            TranscriptRecord.student_id.in_(my_student_ids)).options(
            joinedload(TranscriptRecord.student)).all() if my_student_ids else [])
        yield from emit_array('transcript_records', transcripts, _transcript_to_dict)

        yield from emit_array('departments', Department.query.all(),
                              _department_to_dict)

        courses = Course.query.options(joinedload(Course.department)).all()
        yield from emit_array('courses', courses, _course_to_dict)

        yield from emit_array('graduation_requirements',
                              GraduationRequirement.query.all(), _grad_req_to_dict)

        yield '\n}\n'

    return Response(
        stream_with_context(generate()),
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename={filename}'},
    )


@settings_bp.route('/import-data', methods=['POST'])
@login_required
def import_data():
    """Import caseload and course catalog data from a portable JSON file."""
    file = request.files.get('import_file')
    if not file or not file.filename:
        flash('Please select a file to import.', 'warning')
        return redirect(url_for('settings.index'))

    try:
        raw = file.read().decode('utf-8')
        data = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        flash(f'Invalid file format. Please use a JSON file exported from Counselor Assistant. ({e})', 'danger')
        return redirect(url_for('settings.index'))

    if 'export_version' not in data:
        flash('This file does not appear to be a Counselor Assistant export.', 'danger')
        return redirect(url_for('settings.index'))

    counts = {'students': 0, 'notes': 0, 'service_records': 0,
              'transcript_records': 0, 'departments': 0, 'courses': 0,
              'graduation_requirements': 0, 'tags': 0}

    try:
        # --- School Config ---
        if 'school_config' in data:
            current_user.school_config_json = json.dumps(data['school_config'], ensure_ascii=False)

        # --- Tags ---
        tag_map = {}
        for t_data in data.get('tags', []):
            tag = Tag.query.filter_by(name=t_data['name']).first()
            if not tag:
                tag = Tag(name=t_data['name'], color=t_data.get('color', '#6c757d'))
                db.session.add(tag)
                counts['tags'] += 1
            tag_map[t_data['name']] = tag

        db.session.flush()

        # --- Students ---
        student_map = {}
        for s_data in data.get('students', []):
            sid = s_data['student_id_number']
            student = Student.query.filter_by(student_id_number=sid).first()
            if not student:
                student = Student(student_id_number=sid)
                db.session.add(student)
                counts['students'] += 1

            # Update fields
            for field in ['first_name', 'last_name', 'grade_level', 'gender',
                          'ethnicity', 'email', 'phone', 'parent_guardian_name',
                          'parent_guardian_phone', 'parent_guardian_email',
                          'address', 'homeroom', 'status', 'iep_status',
                          'section_504', 'el_status', 'el_level',
                          'special_programs', 'notes_text']:
                if field in s_data and s_data[field] is not None:
                    setattr(student, field, s_data[field])

            student.date_of_birth = _parse_date(s_data.get('date_of_birth'))
            student.enrollment_date = _parse_date(s_data.get('enrollment_date'))

            # Assign counselor to current user if not set
            if not student.assigned_counselor_id:
                student.assigned_counselor_id = current_user.id

            # Tags
            for tag_name in s_data.get('tags', []):
                if tag_name in tag_map and tag_map[tag_name] not in student.tags:
                    student.tags.append(tag_map[tag_name])

            student_map[sid] = student

        db.session.flush()

        # --- Notes (deduplicate by student + session_date + note_type + title) ---
        for n_data in data.get('notes', []):
            sid = n_data.get('student_id_number')
            if not sid or sid not in student_map:
                continue
            student_db_id = student_map[sid].id
            session_date = _parse_date(n_data.get('session_date'))
            # Check for existing note to avoid duplicates on re-import
            existing = Note.query.filter_by(
                student_id=student_db_id,
                session_date=session_date,
                note_type=n_data.get('note_type', 'individual'),
                title=n_data.get('title'),
            ).first()
            if existing:
                # Update follow_up_completed state from import
                if 'follow_up_completed' in n_data:
                    existing.follow_up_completed = n_data['follow_up_completed']
                    existing.follow_up_completed_date = _parse_date(n_data.get('follow_up_completed_date'))
                continue
            note = Note(
                student_id=student_db_id,
                author_id=current_user.id,
                note_type=n_data.get('note_type', 'individual'),
                title=n_data.get('title'),
                content=n_data.get('content', ''),
                session_date=session_date,
                duration_minutes=n_data.get('duration_minutes'),
                asca_domain=n_data.get('asca_domain'),
                asca_standard=n_data.get('asca_standard'),
                topic_category=n_data.get('topic_category'),
                delivery_method=n_data.get('delivery_method'),
                follow_up_needed=n_data.get('follow_up_needed', False),
                follow_up_date=_parse_date(n_data.get('follow_up_date')),
                follow_up_notes=n_data.get('follow_up_notes'),
                follow_up_completed=n_data.get('follow_up_completed', False),
                follow_up_completed_date=_parse_date(n_data.get('follow_up_completed_date')),
                is_confidential=n_data.get('is_confidential', True),
                restricted_access=n_data.get('restricted_access', False),
            )
            db.session.add(note)
            counts['notes'] += 1

        # --- Service Records (deduplicate by student + date + service_type + topic) ---
        for sr_data in data.get('service_records', []):
            sid = sr_data.get('student_id_number')
            if not sid or sid not in student_map:
                continue
            student_db_id = student_map[sid].id
            sr_date = _parse_date(sr_data.get('date')) or date.today()
            existing = ServiceRecord.query.filter_by(
                student_id=student_db_id,
                date=sr_date,
                service_type=sr_data.get('service_type', 'individual_counseling'),
                topic=sr_data.get('topic'),
            ).first()
            if existing:
                continue
            sr = ServiceRecord(
                student_id=student_db_id,
                counselor_id=current_user.id,
                date=sr_date,
                service_type=sr_data.get('service_type', 'individual_counseling'),
                topic=sr_data.get('topic'),
                description=sr_data.get('description'),
                duration_minutes=sr_data.get('duration_minutes'),
                asca_domain=sr_data.get('asca_domain'),
                asca_standard=sr_data.get('asca_standard'),
                delivery_method=sr_data.get('delivery_method'),
                setting=sr_data.get('setting'),
                outcome=sr_data.get('outcome'),
                follow_up_required=sr_data.get('follow_up_required', False),
                follow_up_date=_parse_date(sr_data.get('follow_up_date')),
                referral_made=sr_data.get('referral_made', False),
                referral_to=sr_data.get('referral_to'),
            )
            db.session.add(sr)
            counts['service_records'] += 1

        # --- Transcript Records (deduplicate by student + quarter) ---
        for tr_data in data.get('transcript_records', []):
            sid = tr_data.get('student_id_number')
            if not sid or sid not in student_map:
                continue
            student_db_id = student_map[sid].id
            existing = TranscriptRecord.query.filter_by(
                student_id=student_db_id,
                quarter=tr_data.get('quarter'),
            ).first()
            if existing:
                continue
            tr = TranscriptRecord(
                student_id=student_map[sid].id,
                quarter=tr_data.get('quarter'),
                total_completed=tr_data.get('total_completed', 0),
                total_wip=tr_data.get('total_wip', 0),
                total_needed=tr_data.get('total_needed', 0),
                risk_level=tr_data.get('risk_level'),
                ag_status=tr_data.get('ag_status'),
                ag_areas_met=tr_data.get('ag_areas_met', 0),
                ag_areas_deficient=tr_data.get('ag_areas_deficient', 0),
                cte_completed=tr_data.get('cte_completed', 0),
                cte_level=tr_data.get('cte_level'),
                cte_is_completer=tr_data.get('cte_is_completer', False),
                credits_json=tr_data.get('credits_json'),
                ag_json=tr_data.get('ag_json'),
                import_date=_parse_date(tr_data.get('import_date')),
                created_by_id=current_user.id,
            )
            db.session.add(tr)
            counts['transcript_records'] += 1

        # --- Departments ---
        dept_map = {}
        for d_data in data.get('departments', []):
            dept = Department.query.filter_by(name=d_data['name']).first()
            if not dept:
                dept = Department(
                    name=d_data['name'],
                    description=d_data.get('description'),
                    head=d_data.get('head'),
                    color=d_data.get('color', '#4A90D9'),
                    sort_order=d_data.get('sort_order', 0),
                )
                db.session.add(dept)
                counts['departments'] += 1
            dept_map[d_data['name']] = dept

        db.session.flush()

        # --- Courses ---
        for c_data in data.get('courses', []):
            existing = Course.query.filter_by(course_number=c_data['course_number']).first()
            if existing:
                continue  # Skip duplicates by course number
            dept = dept_map.get(c_data.get('department_name'))
            course = Course(
                department_id=dept.id if dept else None,
                course_number=c_data['course_number'],
                title=c_data.get('title', ''),
                description=c_data.get('description'),
                credits=c_data.get('credits', 1.0),
                grade_levels=c_data.get('grade_levels'),
                prerequisites=c_data.get('prerequisites'),
                corequisites=c_data.get('corequisites'),
                course_type=c_data.get('course_type'),
                subject_area=c_data.get('subject_area'),
                is_weighted=c_data.get('is_weighted', False),
                weight=c_data.get('weight', 0.0),
                meets_requirement=c_data.get('meets_requirement'),
                ncaa_approved=c_data.get('ncaa_approved', False),
                max_enrollment=c_data.get('max_enrollment'),
                semesters=c_data.get('semesters', 2),
                instructor=c_data.get('instructor'),
                room=c_data.get('room'),
                detailed_description=c_data.get('detailed_description'),
                resources=c_data.get('resources'),
                notes=c_data.get('notes'),
                is_active=c_data.get('is_active', True),
                school_year=c_data.get('school_year'),
            )
            db.session.add(course)
            counts['courses'] += 1

        # --- Graduation Requirements ---
        for gr_data in data.get('graduation_requirements', []):
            existing = GraduationRequirement.query.filter_by(name=gr_data['name']).first()
            if not existing:
                gr = GraduationRequirement(
                    name=gr_data['name'],
                    credits_required=gr_data.get('credits_required', 0),
                    description=gr_data.get('description'),
                    qualifying_courses=gr_data.get('qualifying_courses'),
                    sort_order=gr_data.get('sort_order', 0),
                )
                db.session.add(gr)
                counts['graduation_requirements'] += 1

        db.session.commit()

        # Clean up any duplicate notes (from prior imports without dedup)
        dupes_removed = _cleanup_duplicate_notes()

        # Build summary
        parts = []
        if counts['students']:
            parts.append(f"{counts['students']} students")
        if counts['notes']:
            parts.append(f"{counts['notes']} notes")
        if counts['service_records']:
            parts.append(f"{counts['service_records']} service records")
        if counts['transcript_records']:
            parts.append(f"{counts['transcript_records']} transcript records")
        if counts['tags']:
            parts.append(f"{counts['tags']} tags")
        if counts['departments']:
            parts.append(f"{counts['departments']} departments")
        if counts['courses']:
            parts.append(f"{counts['courses']} courses")
        if counts['graduation_requirements']:
            parts.append(f"{counts['graduation_requirements']} grad requirements")

        if dupes_removed:
            parts.append(f"{dupes_removed} duplicate notes cleaned up")

        if parts:
            summary = 'Imported: ' + ', '.join(parts) + '.'
        else:
            summary = 'No new data to import (all records already exist).'

        log_action('import', 'data_transfer', details=summary)
        flash(summary, 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Import failed: {str(e)}', 'danger')

    return redirect(url_for('settings.index'))


@settings_bp.route('/cleanup-duplicates', methods=['POST'])
@login_required
def cleanup_duplicates():
    """Remove duplicate notes from the database."""
    removed = _cleanup_duplicate_notes()
    if removed:
        log_action('cleanup', 'notes', details=f'Removed {removed} duplicate notes')
        flash(f'Cleaned up {removed} duplicate notes.', 'success')
    else:
        flash('No duplicate notes found.', 'info')
    return redirect(url_for('settings.index'))


@settings_bp.route('/alerts', methods=['GET', 'POST'])
@login_required
def alerts():
    """Configure alert thresholds for this counselor."""
    from app.utils.alert_engine import DEFAULT_THRESHOLDS, get_thresholds, refresh_alerts

    current = get_thresholds(current_user)

    if request.method == 'POST':
        new_settings = {}
        for key in DEFAULT_THRESHOLDS.keys():
            val = request.form.get(key, '').strip()
            if val:
                try:
                    new_settings[key] = max(0, int(val))
                except ValueError:
                    pass
        current_user.alert_settings_json = json.dumps(new_settings) if new_settings else ''
        db.session.commit()
        # Refresh today's alerts to reflect the new thresholds
        refresh_alerts(current_user)
        log_action('update', 'alert_settings', details='Updated alert thresholds')
        flash('Alert thresholds updated.', 'success')
        return redirect(url_for('settings.alerts'))

    return render_template('settings/alerts.html',
        thresholds=current, defaults=DEFAULT_THRESHOLDS)


_SY_RE = re.compile(r'^\d{4}-\d{4}$')


def _calendar_view(cal):
    """Shape a SchoolCalendar (or a parser dict) into template-friendly form."""
    if cal is None:
        return None
    if isinstance(cal, dict):
        return {
            'school_year': cal.get('school_year', ''),
            'first_day': cal.get('first_day'),
            'last_day': cal.get('last_day'),
            'quarters': {q['n']: q for q in cal.get('quarters', [])},
            'semesters': {s['n']: s for s in cal.get('semesters', [])},
            'source': cal.get('source', ''),
            'warnings': cal.get('warnings', []),
        }
    return {
        'school_year': cal.school_year,
        'first_day': cal.first_day,
        'last_day': cal.last_day,
        'quarters': {q['n']: q for q in cal.quarters()},
        'semesters': {s['n']: s for s in cal.semesters()},
        'source': cal.source,
        'warnings': [],
    }


def _calendar_from_form(form):
    """Build a structured calendar dict from posted form fields."""
    quarters = []
    for n in (1, 2, 3, 4):
        quarters.append({
            'n': n,
            'start': _parse_date(form.get(f'q{n}_start')),
            'end': _parse_date(form.get(f'q{n}_end')),
            'progress_due': _parse_date(form.get(f'q{n}_progress_due')),
            'final_due': _parse_date(form.get(f'q{n}_final_due')),
        })
    semesters = []
    for n in (1, 2):
        semesters.append({
            'n': n,
            'start': _parse_date(form.get(f's{n}_start')),
            'end': _parse_date(form.get(f's{n}_end')),
            'final_due': _parse_date(form.get(f's{n}_final_due')),
        })
    return {
        'school_year': (form.get('school_year') or '').strip(),
        'first_day': _parse_date(form.get('first_day')),
        'last_day': _parse_date(form.get('last_day')),
        'quarters': quarters,
        'semesters': semesters,
    }


@settings_bp.route('/calendars')
@login_required
def calendars():
    """List district school calendars; optionally pre-fill the form for edit."""
    from app.models.school_calendar import SchoolCalendar

    all_cals = SchoolCalendar.query.order_by(SchoolCalendar.school_year.desc()).all()

    prefill = None
    edit_year = request.args.get('edit')
    if edit_year:
        cal = SchoolCalendar.for_year(edit_year)
        prefill = _calendar_view(cal)

    return render_template('settings/calendars.html',
                           calendars=all_cals,
                           prefill=prefill,
                           current_year=current_school_year())


@settings_bp.route('/calendars/save', methods=['POST'])
@login_required
def save_calendar():
    """Create or update a school calendar from the manual / reviewed form."""
    from app.models.school_calendar import SchoolCalendar

    data = _calendar_from_form(request.form)
    sy = data['school_year']
    if not _SY_RE.match(sy):
        flash('School year must look like "2027-2028".', 'danger')
        return redirect(url_for('settings.calendars'))

    cal = SchoolCalendar.for_year(sy)
    created = cal is None
    if created:
        cal = SchoolCalendar(school_year=sy)
        db.session.add(cal)

    cal.first_day = data['first_day']
    cal.last_day = data['last_day']
    cal.set_quarters(data['quarters'])
    cal.set_semesters(data['semesters'])
    if request.form.get('source'):
        cal.source = request.form.get('source')
    elif created:
        cal.source = 'manual'

    db.session.commit()
    log_action('update', 'school_calendar', details=f'Saved calendar {sy}')
    flash(f'School calendar for {sy} saved.', 'success')
    return redirect(url_for('settings.calendars'))


@settings_bp.route('/calendars/upload', methods=['POST'])
@login_required
def upload_calendar():
    """Parse an uploaded district calendar PDF and pre-fill the form for review."""
    from app.models.school_calendar import SchoolCalendar
    from app.utils.calendar_parser import parse_calendar_pdf

    file = request.files.get('calendar_pdf')
    if not file or not file.filename:
        flash('Please choose a PDF to upload.', 'warning')
        return redirect(url_for('settings.calendars'))
    if not file.filename.lower().endswith('.pdf'):
        flash('Please upload a PDF file.', 'warning')
        return redirect(url_for('settings.calendars'))

    tmp_dir = os.path.join(Config.DATA_DIR if hasattr(Config, 'DATA_DIR') else 'data', 'uploads')
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, f'_calendar_upload_{datetime.now().strftime("%Y%m%d%H%M%S")}.pdf')
    try:
        file.save(tmp_path)
        parsed = parse_calendar_pdf(tmp_path)
    except ValueError as e:
        flash(f'Could not parse this calendar: {e}', 'danger')
        return redirect(url_for('settings.calendars'))
    except Exception:
        flash('Could not read this PDF. Try entering the dates manually.', 'danger')
        return redirect(url_for('settings.calendars'))
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    parsed['source'] = f'pdf:{file.filename}'
    prefill = _calendar_view(parsed)

    all_cals = SchoolCalendar.query.order_by(SchoolCalendar.school_year.desc()).all()
    if prefill['warnings']:
        flash('Review the highlighted fields below — some dates could not be '
              'auto-detected. Then click Save.', 'warning')
    else:
        flash('Calendar parsed. Review the dates below, then click Save.', 'info')
    return render_template('settings/calendars.html',
                           calendars=all_cals,
                           prefill=prefill,
                           current_year=current_school_year())


@settings_bp.route('/calendars/<int:cal_id>/delete', methods=['POST'])
@login_required
def delete_calendar(cal_id):
    from app.models.school_calendar import SchoolCalendar
    cal = SchoolCalendar.query.get_or_404(cal_id)
    sy = cal.school_year
    db.session.delete(cal)
    db.session.commit()
    log_action('delete', 'school_calendar', details=f'Deleted calendar {sy}')
    flash(f'Deleted calendar for {sy}.', 'success')
    return redirect(url_for('settings.calendars'))


@settings_bp.route('/factory-reset', methods=['POST'])
@login_required
def factory_reset():
    """Delete all data and restart the setup wizard."""
    from flask_login import logout_user
    from flask import current_app
    log_action('delete', 'factory_reset', details='Full factory reset initiated')
    logout_user()
    db.session.remove()  # close connections so we can delete the file
    db_path = Config.SQLALCHEMY_DATABASE_URI.replace('sqlite:///', '')
    if os.path.exists(db_path):
        os.remove(db_path)
    uploads_dir = os.path.join(Config.BASE_DIR, 'data', 'uploads')
    if os.path.isdir(uploads_dir):
        shutil.rmtree(uploads_dir)
        os.makedirs(uploads_dir, exist_ok=True)
    schema_hash = os.path.join(Config.BASE_DIR, 'data', '.schema_hash')
    if os.path.exists(schema_hash):
        os.remove(schema_hash)
    # Re-create the empty schema so the next request can query users/students
    db.create_all()
    # Force the before_request handler to re-check setup status
    if hasattr(current_app, '_setup_done'):
        current_app._setup_done = False
    return redirect('/setup')
