from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app import db
from app.models.course import Course, Department, GraduationRequirement
from app.utils.audit import log_action

course_catalog_bp = Blueprint('course_catalog', __name__)


@course_catalog_bp.route('/')
@login_required
def index():
    search = request.args.get('search', '').strip()
    dept_id = request.args.get('department', '')
    course_type = request.args.get('type', '')
    grade = request.args.get('grade', '')

    query = Course.query.filter_by(is_active=True)

    if search:
        query = query.filter(
            db.or_(
                Course.title.ilike(f'%{search}%'),
                Course.course_number.ilike(f'%{search}%'),
                Course.description.ilike(f'%{search}%'),
            )
        )
    if dept_id:
        query = query.filter_by(department_id=int(dept_id))
    if course_type:
        query = query.filter_by(course_type=course_type)
    if grade:
        query = query.filter(Course.grade_levels.contains(grade))

    courses = query.order_by(Course.department_id, Course.course_number).all()
    departments = Department.query.order_by(Department.sort_order, Department.name).all()

    return render_template('course_catalog/index.html',
        courses=courses, departments=departments, search=search,
        dept_id=dept_id, course_type=course_type, grade=grade,
        course_types=Course.COURSE_TYPES)


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
