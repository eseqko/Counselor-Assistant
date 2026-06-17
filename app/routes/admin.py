"""Admin panel — user management, department dashboard, caseload equity."""
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from app import db
from app.models.user import User
from app.models.student import Student
from app.models.note import Note
from app.models.service_record import ServiceRecord
from app.models.ai_tool_history import AIToolHistory
from app.utils.roles import admin_required
from app.utils.audit import log_action
from datetime import date, datetime, timedelta
from sqlalchemy import func

admin_bp = Blueprint('admin', __name__, template_folder='../templates/admin')


@admin_bp.route('/')
@login_required
@admin_required
def index():
    counselors = User.query.order_by(User.display_name).all()
    # Exclude shadow students (school-wide comparison data) and per-user Sample
    # Students (screener test vehicles) from real caseload metrics.
    total_students = Student.query.filter_by(
        status='active', is_shadow=False, is_sample=False).count()
    unassigned = Student.query.filter(
        (Student.assigned_counselor_id == None) | (Student.assigned_counselor_id == 0),
        Student.status == 'active',
        Student.is_shadow == False,
        Student.is_sample == False,
    ).count()

    thirty_days = date.today() - timedelta(days=30)
    stats = []
    for c in counselors:
        caseload = Student.query.filter_by(
            assigned_counselor_id=c.id, status='active', is_sample=False).count()
        notes_30d = Note.query.filter(
            Note.author_id == c.id, Note.session_date >= thirty_days
        ).count()
        services_30d = ServiceRecord.query.filter(
            ServiceRecord.counselor_id == c.id, ServiceRecord.date >= thirty_days
        ).count()
        ai_uses = AIToolHistory.query.filter(
            AIToolHistory.user_id == c.id, AIToolHistory.created_at >= datetime.combine(thirty_days, datetime.min.time())
        ).count()
        stats.append({
            'user': c,
            'caseload': caseload,
            'notes_30d': notes_30d,
            'services_30d': services_30d,
            'ai_uses': ai_uses,
        })

    return render_template('admin/index.html',
                           counselors=counselors,
                           stats=stats,
                           total_students=total_students,
                           unassigned=unassigned)


@admin_bp.route('/users')
@login_required
@admin_required
def users():
    all_users = User.query.order_by(User.display_name).all()
    return render_template('admin/users.html', users=all_users)


@admin_bp.route('/users/add', methods=['POST'])
@login_required
@admin_required
def add_user():
    username = request.form.get('username', '').strip()
    display_name = request.form.get('display_name', '').strip()
    password = request.form.get('password', '').strip()
    role = request.form.get('role', 'counselor')

    if not username or not password:
        flash('Username and password are required.', 'error')
        return redirect(url_for('admin.users'))

    if len(password) < 8:
        flash('Password must be at least 8 characters.', 'error')
        return redirect(url_for('admin.users'))

    if User.query.filter_by(username=username).first():
        flash(f'Username "{username}" already exists.', 'error')
        return redirect(url_for('admin.users'))

    if role not in ('counselor', 'admin'):
        role = 'counselor'

    user = User(
        username=username,
        display_name=display_name or username,
        role=role,
        setup_completed=True,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    log_action('user_create', 'user', user.id, f'Created user: {username} ({role})')
    flash(f'User "{display_name or username}" created.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    display_name = request.form.get('display_name', '').strip()
    role = request.form.get('role', user.role)
    new_password = request.form.get('new_password', '').strip()

    if display_name:
        user.display_name = display_name
    if role in ('counselor', 'admin'):
        user.role = role
    if new_password:
        if len(new_password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return redirect(url_for('admin.users'))
        user.set_password(new_password)

    db.session.commit()
    log_action('user_edit', 'user', user.id, f'Edited user: {user.username}')
    flash(f'User "{user.display_name}" updated.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('admin.users'))

    name = user.display_name
    db.session.delete(user)
    db.session.commit()
    log_action('user_delete', 'user', user_id, f'Deleted user: {name}')
    flash(f'User "{name}" deleted.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/caseload-equity')
@login_required
@admin_required
def caseload_equity():
    counselors = User.query.filter_by(role='counselor').order_by(User.display_name).all()
    if not counselors:
        counselors = User.query.order_by(User.display_name).all()

    equity_data = []
    for c in counselors:
        students = Student.query.filter_by(
            assigned_counselor_id=c.id, status='active', is_sample=False)
        total = students.count()
        by_grade = db.session.query(
            Student.grade_level, func.count(Student.id)
        ).filter_by(assigned_counselor_id=c.id, status='active', is_sample=False
                    ).group_by(Student.grade_level).all()
        iep_count = students.filter(Student.iep_status == True).count()
        s504_count = students.filter(Student.section_504 == True).count()
        el_count = students.filter(Student.el_status.notin_(['', 'EO', None])).count()

        equity_data.append({
            'user': c,
            'total': total,
            'by_grade': dict(by_grade),
            'iep': iep_count,
            's504': s504_count,
            'el': el_count,
        })

    unassigned = Student.query.filter(
        (Student.assigned_counselor_id == None) | (Student.assigned_counselor_id == 0),
        Student.status == 'active',
        Student.is_shadow == False,
        Student.is_sample == False,
    ).order_by(Student.last_name, Student.first_name).all()

    return render_template('admin/caseload_equity.html',
                           equity_data=equity_data,
                           unassigned=unassigned,
                           counselors=counselors)


@admin_bp.route('/reassign', methods=['POST'])
@login_required
@admin_required
def reassign_students():
    data = request.get_json()
    student_ids = data.get('student_ids', [])
    counselor_id = data.get('counselor_id')

    if not student_ids or not counselor_id:
        return jsonify({'ok': False, 'error': 'Missing data'}), 400

    counselor = User.query.get(counselor_id)
    if not counselor:
        return jsonify({'ok': False, 'error': 'Counselor not found'}), 404

    count = Student.query.filter(Student.id.in_(student_ids)).update(
        {Student.assigned_counselor_id: counselor_id}, synchronize_session='fetch'
    )
    db.session.commit()
    log_action('caseload_reassign', 'student', None,
               f'Reassigned {count} students to {counselor.display_name}')
    return jsonify({'ok': True, 'count': count, 'message': f'{count} students reassigned to {counselor.display_name}.'})
