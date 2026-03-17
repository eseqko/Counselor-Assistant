import json
import os
import shutil
from datetime import datetime, date, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, Response
from flask_login import login_required, current_user
from app import db
from app.models.user import User, AuditLog
from app.models.student import Student, Tag, student_tags
from app.models.note import Note
from app.models.service_record import ServiceRecord
from app.models.transcript import TranscriptRecord
from app.models.course import Department, Course, GraduationRequirement
from app.utils.audit import log_action
from config import Config

settings_bp = Blueprint('settings', __name__)


@settings_bp.route('/')
@login_required
def index():
    return render_template('settings/index.html')


@settings_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_user.display_name = request.form.get('display_name', current_user.display_name)
        current_user.school_name = request.form.get('school_name', '')
        db.session.commit()
        flash('Profile updated.', 'success')
        return redirect(url_for('settings.profile'))

    return render_template('settings/profile.html')


@settings_bp.route('/audit-log')
@login_required
def audit_log():
    page = request.args.get('page', 1, type=int)
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).paginate(
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
        flash(f'Backup created successfully at {backup_path}', 'success')
    except Exception as e:
        flash(f'Backup failed: {str(e)}', 'danger')

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


@settings_bp.route('/export-data')
@login_required
def export_data():
    """Export caseload and course catalog data as a portable JSON file."""
    data = {
        'export_version': 1,
        'exported_at': datetime.now(timezone.utc).isoformat(),
        'exported_by': current_user.display_name or current_user.username,
    }

    # --- Tags ---
    data['tags'] = [
        {'name': t.name, 'color': t.color}
        for t in Tag.query.all()
    ]

    # --- Students ---
    students_list = []
    for s in Student.query.all():
        students_list.append({
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
        })
    data['students'] = students_list

    # --- Notes ---
    data['notes'] = [
        {
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
            'is_confidential': n.is_confidential,
            'restricted_access': n.restricted_access,
            'created_at': _serialize_date(n.created_at),
        }
        for n in Note.query.all()
    ]

    # --- Service Records ---
    data['service_records'] = [
        {
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
        for sr in ServiceRecord.query.all()
    ]

    # --- Transcript Records ---
    data['transcript_records'] = [
        {
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
        for tr in TranscriptRecord.query.all()
    ]

    # --- Departments ---
    data['departments'] = [
        {
            'name': d.name,
            'description': d.description,
            'head': d.head,
            'color': d.color,
            'sort_order': d.sort_order,
        }
        for d in Department.query.all()
    ]

    # --- Courses ---
    data['courses'] = [
        {
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
        for c in Course.query.all()
    ]

    # --- Graduation Requirements ---
    data['graduation_requirements'] = [
        {
            'name': gr.name,
            'credits_required': gr.credits_required,
            'description': gr.description,
            'qualifying_courses': gr.qualifying_courses,
            'sort_order': gr.sort_order,
        }
        for gr in GraduationRequirement.query.all()
    ]

    # Build filename
    school = (current_user.school_name or 'export').replace(' ', '_')
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    filename = f'counselor_data_{school}_{timestamp}.json'

    json_str = json.dumps(data, indent=2, ensure_ascii=False)
    log_action('export', 'data_transfer', details=f'Exported portable data file: {filename}')

    return Response(
        json_str,
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
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

        # --- Notes ---
        for n_data in data.get('notes', []):
            sid = n_data.get('student_id_number')
            if not sid or sid not in student_map:
                continue
            note = Note(
                student_id=student_map[sid].id,
                author_id=current_user.id,
                note_type=n_data.get('note_type', 'individual'),
                title=n_data.get('title'),
                content=n_data.get('content', ''),
                session_date=_parse_date(n_data.get('session_date')),
                duration_minutes=n_data.get('duration_minutes'),
                asca_domain=n_data.get('asca_domain'),
                asca_standard=n_data.get('asca_standard'),
                topic_category=n_data.get('topic_category'),
                delivery_method=n_data.get('delivery_method'),
                follow_up_needed=n_data.get('follow_up_needed', False),
                follow_up_date=_parse_date(n_data.get('follow_up_date')),
                follow_up_notes=n_data.get('follow_up_notes'),
                is_confidential=n_data.get('is_confidential', True),
                restricted_access=n_data.get('restricted_access', False),
            )
            db.session.add(note)
            counts['notes'] += 1

        # --- Service Records ---
        for sr_data in data.get('service_records', []):
            sid = sr_data.get('student_id_number')
            if not sid or sid not in student_map:
                continue
            sr = ServiceRecord(
                student_id=student_map[sid].id,
                counselor_id=current_user.id,
                date=_parse_date(sr_data.get('date')) or date.today(),
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

        # --- Transcript Records ---
        for tr_data in data.get('transcript_records', []):
            sid = tr_data.get('student_id_number')
            if not sid or sid not in student_map:
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
