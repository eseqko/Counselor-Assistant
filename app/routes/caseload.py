from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models.student import Student, Tag
from app.utils.audit import log_action
from app.utils.helpers import parse_date

caseload_bp = Blueprint('caseload', __name__)


@caseload_bp.route('/')
@login_required
def index():
    search = request.args.get('search', '').strip()
    grade = request.args.get('grade', '')
    status = request.args.get('status', 'active')
    tag_filter = request.args.get('tag', '')

    query = Student.query.filter_by(assigned_counselor_id=current_user.id)

    if status:
        query = query.filter_by(status=status)
    if grade:
        query = query.filter_by(grade_level=int(grade))
    if search:
        query = query.filter(
            db.or_(
                Student.first_name.ilike(f'%{search}%'),
                Student.last_name.ilike(f'%{search}%'),
                Student.student_id_number.ilike(f'%{search}%'),
            )
        )
    if tag_filter:
        query = query.filter(Student.tags.any(Tag.name == tag_filter))

    students = query.order_by(Student.last_name, Student.first_name).all()
    tags = Tag.query.order_by(Tag.name).all()

    return render_template('caseload/index.html',
        students=students, search=search, grade=grade,
        status=status, tag_filter=tag_filter, tags=tags)


@caseload_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_student():
    if request.method == 'POST':
        student = Student(
            student_id_number=request.form['student_id_number'],
            first_name=request.form['first_name'],
            last_name=request.form['last_name'],
            grade_level=int(request.form['grade_level']) if request.form.get('grade_level') else None,
            date_of_birth=parse_date(request.form.get('date_of_birth')),
            gender=request.form.get('gender', ''),
            ethnicity=request.form.get('ethnicity', ''),
            email=request.form.get('email', ''),
            phone=request.form.get('phone', ''),
            parent_guardian_name=request.form.get('parent_guardian_name', ''),
            parent_guardian_phone=request.form.get('parent_guardian_phone', ''),
            parent_guardian_email=request.form.get('parent_guardian_email', ''),
            address=request.form.get('address', ''),
            homeroom=request.form.get('homeroom', ''),
            assigned_counselor_id=current_user.id,
            iep_status='iep_status' in request.form,
            section_504='section_504' in request.form,
            ell_status='ell_status' in request.form,
            enrollment_date=parse_date(request.form.get('enrollment_date')),
        )
        # Handle tags
        tag_names = request.form.get('tags', '').split(',')
        for name in tag_names:
            name = name.strip()
            if name:
                tag = Tag.query.filter_by(name=name).first()
                if not tag:
                    tag = Tag(name=name)
                    db.session.add(tag)
                student.tags.append(tag)

        db.session.add(student)
        db.session.commit()
        log_action('create', 'student', student.id, f'Added student {student.full_name}')
        flash(f'Student {student.full_name} added successfully.', 'success')
        return redirect(url_for('caseload.view_student', id=student.id))

    tags = Tag.query.order_by(Tag.name).all()
    return render_template('caseload/add.html', tags=tags)


@caseload_bp.route('/<int:id>')
@login_required
def view_student(id):
    student = Student.query.get_or_404(id)
    log_action('view', 'student', student.id)
    notes = student.notes.limit(10).all()
    services = student.service_records.limit(10).all()
    return render_template('caseload/view.html',
        student=student, notes=notes, services=services)


@caseload_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_student(id):
    student = Student.query.get_or_404(id)

    if request.method == 'POST':
        student.student_id_number = request.form['student_id_number']
        student.first_name = request.form['first_name']
        student.last_name = request.form['last_name']
        student.grade_level = int(request.form['grade_level']) if request.form.get('grade_level') else None
        student.date_of_birth = parse_date(request.form.get('date_of_birth'))
        student.gender = request.form.get('gender', '')
        student.ethnicity = request.form.get('ethnicity', '')
        student.email = request.form.get('email', '')
        student.phone = request.form.get('phone', '')
        student.parent_guardian_name = request.form.get('parent_guardian_name', '')
        student.parent_guardian_phone = request.form.get('parent_guardian_phone', '')
        student.parent_guardian_email = request.form.get('parent_guardian_email', '')
        student.address = request.form.get('address', '')
        student.homeroom = request.form.get('homeroom', '')
        student.status = request.form.get('status', 'active')
        student.iep_status = 'iep_status' in request.form
        student.section_504 = 'section_504' in request.form
        student.ell_status = 'ell_status' in request.form

        db.session.commit()
        log_action('update', 'student', student.id, f'Updated student {student.full_name}')
        flash(f'Student {student.full_name} updated.', 'success')
        return redirect(url_for('caseload.view_student', id=student.id))

    tags = Tag.query.order_by(Tag.name).all()
    return render_template('caseload/edit.html', student=student, tags=tags)


@caseload_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete_student(id):
    student = Student.query.get_or_404(id)
    name = student.full_name
    log_action('delete', 'student', student.id, f'Deleted student {name}')
    db.session.delete(student)
    db.session.commit()
    flash(f'Student {name} removed from caseload.', 'warning')
    return redirect(url_for('caseload.index'))
