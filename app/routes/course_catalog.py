import json
import io
import os
import zipfile
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, jsonify, send_from_directory, send_file)
from flask_login import login_required, current_user
from app import db, csrf
from app.models.course import Course, Department, GraduationRequirement
from app.utils.audit import log_action

course_catalog_bp = Blueprint('course_catalog', __name__)

CATALOG_DIR = os.path.join(
    os.path.abspath(os.path.dirname(__file__)), '..', 'static', 'course_catalog'
)


@course_catalog_bp.route('/')
@login_required
def index():
    return render_template('course_catalog/index.html')


@course_catalog_bp.route('/course/<int:id>')
@login_required
def view_course(id):
    course = Course.query.get_or_404(id)
    log_action('view', 'course', course.id)
    return render_template('course_catalog/view.html', course=course)


@course_catalog_bp.route('/course/add', methods=['GET', 'POST'])
@login_required
def add_course():
    if request.method == 'POST':
        course = Course(
            course_number=request.form['course_number'],
            title=request.form['title'],
            description=request.form.get('description', ''),
            department_id=int(request.form['department_id']) if request.form.get('department_id') else None,
            credits=float(request.form.get('credits', 1.0)),
            grade_levels=request.form.get('grade_levels', ''),
            prerequisites=request.form.get('prerequisites', ''),
            course_type=request.form.get('course_type', 'elective'),
            subject_area=request.form.get('subject_area', ''),
            is_weighted='is_weighted' in request.form,
            weight=float(request.form.get('weight', 0)),
            meets_requirement=request.form.get('meets_requirement', ''),
            ncaa_approved='ncaa_approved' in request.form,
            semesters=int(request.form.get('semesters', 2)),
            max_enrollment=int(request.form['max_enrollment']) if request.form.get('max_enrollment') else None,
            instructor=request.form.get('instructor', ''),
            detailed_description=request.form.get('detailed_description', ''),
            notes=request.form.get('notes', ''),
            school_year=request.form.get('school_year', ''),
        )
        db.session.add(course)
        db.session.commit()
        log_action('create', 'course', course.id)
        flash(f'Course {course.course_number} added.', 'success')
        return redirect(url_for('course_catalog.view_course', id=course.id))

    departments = Department.query.order_by(Department.name).all()
    return render_template('course_catalog/add.html',
        departments=departments, course_types=Course.COURSE_TYPES)


@course_catalog_bp.route('/course/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_course(id):
    course = Course.query.get_or_404(id)

    if request.method == 'POST':
        course.course_number = request.form['course_number']
        course.title = request.form['title']
        course.description = request.form.get('description', '')
        course.department_id = int(request.form['department_id']) if request.form.get('department_id') else None
        course.credits = float(request.form.get('credits', 1.0))
        course.grade_levels = request.form.get('grade_levels', '')
        course.prerequisites = request.form.get('prerequisites', '')
        course.course_type = request.form.get('course_type', 'elective')
        course.is_weighted = 'is_weighted' in request.form
        course.weight = float(request.form.get('weight', 0))
        course.meets_requirement = request.form.get('meets_requirement', '')
        course.ncaa_approved = 'ncaa_approved' in request.form
        course.semesters = int(request.form.get('semesters', 2))
        course.detailed_description = request.form.get('detailed_description', '')
        course.notes = request.form.get('notes', '')
        course.school_year = request.form.get('school_year', '')

        db.session.commit()
        log_action('update', 'course', course.id)
        flash('Course updated.', 'success')
        return redirect(url_for('course_catalog.view_course', id=course.id))

    departments = Department.query.order_by(Department.name).all()
    return render_template('course_catalog/edit.html',
        course=course, departments=departments, course_types=Course.COURSE_TYPES)


@course_catalog_bp.route('/departments', methods=['GET', 'POST'])
@login_required
def departments():
    if request.method == 'POST':
        dept = Department(
            name=request.form['name'],
            description=request.form.get('description', ''),
            head=request.form.get('head', ''),
            color=request.form.get('color', '#4A90D9'),
        )
        db.session.add(dept)
        db.session.commit()
        flash(f'Department {dept.name} added.', 'success')
        return redirect(url_for('course_catalog.departments'))

    depts = Department.query.order_by(Department.sort_order, Department.name).all()
    return render_template('course_catalog/departments.html', departments=depts)


@course_catalog_bp.route('/requirements')
@login_required
def requirements():
    reqs = GraduationRequirement.query.order_by(GraduationRequirement.sort_order).all()
    return render_template('course_catalog/requirements.html', requirements=reqs)


@course_catalog_bp.route('/requirements/add', methods=['POST'])
@login_required
def add_requirement():
    req = GraduationRequirement(
        name=request.form['name'],
        credits_required=float(request.form['credits_required']),
        description=request.form.get('description', ''),
        qualifying_courses=request.form.get('qualifying_courses', ''),
    )
    db.session.add(req)
    db.session.commit()
    flash('Graduation requirement added.', 'success')
    return redirect(url_for('course_catalog.requirements'))


DEPT_CODE_MAP = {
    'social-science': 'Social Science',
    'english': 'English',
    'mathematics': 'Mathematics',
    'science': 'Science',
    'lote': 'Languages (LOTE)',
    'vpa': 'Visual & Performing Arts',
    'cte': 'Career Technical Ed',
    'pe': 'PE & Health',
    'electives': 'Interdisciplinary Electives',
    'special-ed': 'Special Ed',
}

TYPE_MAP = {
    'cp': 'required',
    'ap': 'ap',
    'eld': 'elective',
    'sp': 'elective',
}


def _expand_grade_range(grade_str):
    """Convert '9-12' or '11-12' to '9,10,11,12' format."""
    if not grade_str:
        return ''
    grade_str = grade_str.strip()
    if '-' in grade_str:
        parts = grade_str.split('-')
        try:
            start, end = int(parts[0]), int(parts[1])
            return ','.join(str(g) for g in range(start, end + 1))
        except (ValueError, IndexError):
            pass
    # Already a single grade or comma-separated
    return grade_str.replace(' ', '')


def _get_or_create_dept(dept_code):
    """Get or create a Department from a localStorage dept code."""
    name = DEPT_CODE_MAP.get(dept_code, dept_code.replace('-', ' ').title())
    dept = Department.query.filter_by(name=name).first()
    if not dept:
        dept = Department(name=name)
        db.session.add(dept)
        db.session.flush()
    return dept


@course_catalog_bp.route('/api/sync-courses', methods=['POST'])
@csrf.exempt
@login_required
def sync_courses():
    """Sync courses from browser localStorage into the database."""
    data = request.get_json(silent=True) or {}
    courses_data = data.get('courses', [])
    info_data = data.get('info')

    if not courses_data:
        return jsonify({'ok': False, 'error': 'No courses provided'}), 400

    try:
        return _do_sync_courses(courses_data, info_data)
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500


def _do_sync_courses(courses_data, info_data):
    synced = 0
    skipped = 0

    for c in courses_data:
        # Skip inactive courses
        if c.get('inactive'):
            skipped += 1
            continue

        name = (c.get('name') or '').strip()
        if not name:
            skipped += 1
            continue

        # Use course code as course_number, or generate from id
        code = (c.get('code') or c.get('id') or '').strip()
        if not code:
            skipped += 1
            continue

        # Check if course already exists by code
        existing = Course.query.filter_by(course_number=code).first()
        if existing:
            # Update existing course
            course = existing
        else:
            course = Course(course_number=code, title=name)
            db.session.add(course)

        course.title = name

        # Map department
        dept_code = c.get('dept', '')
        if dept_code:
            dept = _get_or_create_dept(dept_code)
            course.department_id = dept.id
            course.subject_area = dept.name
        course.description = c.get('desc', '')

        # Credits: localStorage stores as string like "10" or "5"
        try:
            course.credits = float(c.get('credits', 10))
        except (ValueError, TypeError):
            course.credits = 10.0

        course.grade_levels = _expand_grade_range(c.get('grade', ''))
        course.prerequisites = c.get('prereq', '') if c.get('prereq', 'None') != 'None' else ''

        # Course type mapping
        ls_type = c.get('type', 'cp')
        course.course_type = TYPE_MAP.get(ls_type, 'elective')
        if ls_type == 'ap':
            course.is_weighted = True
            course.weight = 1.0

        # a-g requirement
        ag = c.get('ag', '')
        if ag:
            course.meets_requirement = 'a-g:' + ag

        # Full year
        course.semesters = 2 if c.get('fullYear') else 1
        course.is_active = True

        synced += 1

    # Sync graduation requirements from info data
    grad_synced = 0
    if info_data and info_data.get('gradReqs'):
        for i, req in enumerate(info_data['gradReqs']):
            area = req.get('subject', req.get('area', ''))
            if not area:
                continue
            existing_req = GraduationRequirement.query.filter_by(name=area).first()
            if existing_req:
                gr = existing_req
            else:
                gr = GraduationRequirement(name=area)
                db.session.add(gr)

            # Parse credits from strings like "30 credits"
            juhsd_str = req.get('juhsd', '')
            try:
                cr = float(''.join(ch for ch in juhsd_str if ch.isdigit() or ch == '.'))
            except ValueError:
                cr = 0
            gr.credits_required = cr
            gr.description = req.get('note', '')
            gr.sort_order = i
            grad_synced += 1

    db.session.commit()
    log_action('sync', 'course_catalog', None)

    return jsonify({
        'ok': True,
        'synced': synced,
        'skipped': skipped,
        'grad_requirements': grad_synced,
    })


@course_catalog_bp.route('/api/school-config', methods=['GET'])
@login_required
def get_school_config():
    """Return the server-stored school config for the current user."""
    raw = current_user.school_config_json
    if raw:
        try:
            return jsonify(json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            pass
    return jsonify({})


@course_catalog_bp.route('/api/school-config', methods=['POST'])
@csrf.exempt
@login_required
def save_school_config():
    """Persist the school config to the database so it survives device transfers."""
    data = request.get_json(silent=True) or {}
    current_user.school_config_json = json.dumps(data, ensure_ascii=False)
    db.session.commit()
    return jsonify({'ok': True})


# =====================================================================
#  PUBLIC CATALOG (no login required — replaces run_catalog.py)
# =====================================================================

@course_catalog_bp.route('/public')
def public_catalog():
    """Serve the catalog viewer without authentication."""
    return send_from_directory(CATALOG_DIR, 'index.html')


@course_catalog_bp.route('/public/editor')
def public_editor():
    return send_from_directory(CATALOG_DIR, 'editor.html')


@course_catalog_bp.route('/public/setup')
def public_setup():
    return send_from_directory(CATALOG_DIR, 'setup.html')


@course_catalog_bp.route('/public/<path:filename>')
def public_files(filename):
    """Serve static files referenced by the catalog pages."""
    filepath = os.path.join(CATALOG_DIR, filename)
    if os.path.isfile(filepath):
        return send_from_directory(CATALOG_DIR, filename)
    return send_from_directory(
        os.path.join(os.path.dirname(CATALOG_DIR)), filename
    )


# =====================================================================
#  EXPORT (ZIP download)
# =====================================================================

@course_catalog_bp.route('/export-zip')
@login_required
def export_zip():
    """Download the catalog as a self-contained ZIP folder.

    Bundles index.html, editor.html, setup.html, and school-config.js
    into a ZIP file ready to host on any static server or open locally.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fname in ('index.html', 'editor.html', 'setup.html',
                       'school-config.js', 'importer.js'):
            fpath = os.path.join(CATALOG_DIR, fname)
            if os.path.isfile(fpath):
                zf.write(fpath, f'course-catalog/{fname}')
    buf.seek(0)
    return send_file(
        buf,
        mimetype='application/zip',
        as_attachment=True,
        download_name='Course_Catalog_Export.zip',
    )
