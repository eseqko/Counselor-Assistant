from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models.goal import Goal, GoalProgress
from app.models.student import Student
from app.utils.audit import log_action
from app.utils.helpers import parse_date
from app.utils.roles import owned_or_404, caseload_student_or_404

goals_bp = Blueprint('goals', __name__)


@goals_bp.route('/')
@login_required
def index():
    student_id = request.args.get('student_id', '')
    status = request.args.get('status', '')
    domain = request.args.get('domain', '')

    query = Goal.query.filter_by(counselor_id=current_user.id)
    if student_id:
        query = query.filter_by(student_id=int(student_id))
    if status:
        if status == 'open':
            query = query.filter(Goal.status.in_(['active', 'in_progress']))
        else:
            query = query.filter_by(status=status)
    if domain:
        query = query.filter_by(asca_domain=domain)

    goals = query.order_by(Goal.target_date.asc().nullslast(), Goal.created_at.desc()).all()
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active'
    ).order_by(Student.last_name).all()

    return render_template('goals/index.html',
        goals=goals, students=students,
        student_id=student_id, status=status, domain=domain,
        statuses=Goal.STATUSES, domains=Goal.ASCA_DOMAINS)


@goals_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if request.method == 'POST':
        subject = caseload_student_or_404(request.form.get('student_id'))
        goal = Goal(
            student_id=subject.id,
            counselor_id=current_user.id,
            title=request.form['title'].strip(),
            description=request.form.get('description', '').strip(),
            asca_domain=request.form.get('asca_domain', ''),
            asca_mindset=request.form.get('asca_mindset', '').strip(),
            baseline=request.form.get('baseline', '').strip(),
            target=request.form.get('target', '').strip(),
            measurement_method=request.form.get('measurement_method', '').strip(),
            strategy=request.form.get('strategy', '').strip(),
            start_date=parse_date(request.form.get('start_date')) or date.today(),
            target_date=parse_date(request.form.get('target_date')),
            status=request.form.get('status', 'active'),
        )
        db.session.add(goal)
        db.session.commit()
        log_action('create', 'goal', goal.id, f'Created goal: {goal.title}')
        flash('Goal created.', 'success')
        return redirect(url_for('goals.view', id=goal.id))

    student_id = request.args.get('student_id', '')
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active'
    ).order_by(Student.last_name).all()
    return render_template('goals/add.html',
        students=students, preselected_student=student_id,
        domains=Goal.ASCA_DOMAINS, statuses=Goal.STATUSES)


@goals_bp.route('/<int:id>')
@login_required
def view(id):
    goal = owned_or_404(Goal, id)
    log_action('view', 'goal', goal.id)
    return render_template('goals/view.html', goal=goal,
        statuses=Goal.STATUSES)


@goals_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    goal = owned_or_404(Goal, id)
    if request.method == 'POST':
        goal.title = request.form['title'].strip()
        goal.description = request.form.get('description', '').strip()
        goal.asca_domain = request.form.get('asca_domain', '')
        goal.asca_mindset = request.form.get('asca_mindset', '').strip()
        goal.baseline = request.form.get('baseline', '').strip()
        goal.target = request.form.get('target', '').strip()
        goal.measurement_method = request.form.get('measurement_method', '').strip()
        goal.strategy = request.form.get('strategy', '').strip()
        goal.start_date = parse_date(request.form.get('start_date')) or goal.start_date
        goal.target_date = parse_date(request.form.get('target_date'))
        goal.status = request.form.get('status', goal.status)
        if request.form.get('progress_percent'):
            try:
                goal.progress_percent = max(0, min(100, int(request.form['progress_percent'])))
            except ValueError:
                pass
        goal.outcome = request.form.get('outcome', '').strip()
        if goal.status == 'achieved' and not goal.completed_date:
            goal.completed_date = date.today()
        db.session.commit()
        log_action('update', 'goal', goal.id)
        flash('Goal updated.', 'success')
        return redirect(url_for('goals.view', id=goal.id))

    return render_template('goals/edit.html', goal=goal,
        domains=Goal.ASCA_DOMAINS, statuses=Goal.STATUSES)


@goals_bp.route('/<int:id>/progress', methods=['POST'])
@login_required
def add_progress(id):
    goal = owned_or_404(Goal, id)
    entry = GoalProgress(
        goal_id=goal.id,
        entry_date=parse_date(request.form.get('entry_date')) or date.today(),
        metric_value=request.form.get('metric_value', '').strip(),
        progress_percent=int(request.form['progress_percent']) if request.form.get('progress_percent') else None,
        note=request.form.get('note', '').strip(),
    )
    db.session.add(entry)
    if entry.progress_percent is not None:
        goal.progress_percent = max(0, min(100, entry.progress_percent))
    db.session.commit()
    log_action('create', 'goal_progress', entry.id, f'Goal {goal.id}')
    flash('Progress recorded.', 'success')
    return redirect(url_for('goals.view', id=goal.id))


@goals_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    goal = owned_or_404(Goal, id)
    log_action('delete', 'goal', goal.id)
    db.session.delete(goal)
    db.session.commit()
    flash('Goal deleted.', 'warning')
    return redirect(url_for('goals.index'))
