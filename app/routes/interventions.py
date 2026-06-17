from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models.intervention import InterventionPlan, InterventionProgress
from app.models.student import Student
from app.utils.audit import log_action
from app.utils.helpers import parse_date
from app.utils.roles import owned_or_404, caseload_student_or_404

interventions_bp = Blueprint('interventions', __name__)


@interventions_bp.route('/')
@login_required
def index():
    student_id = request.args.get('student_id', '')
    tier = request.args.get('tier', '')
    status = request.args.get('status', 'active')

    query = InterventionPlan.query.filter_by(counselor_id=current_user.id)
    if student_id:
        query = query.filter_by(student_id=int(student_id))
    if tier:
        query = query.filter_by(tier=int(tier))
    if status:
        query = query.filter_by(status=status)

    plans = query.order_by(InterventionPlan.tier.desc(),
                           InterventionPlan.start_date.desc()).all()

    # Build pyramid counts (active only — one grouped query)
    from sqlalchemy import func
    pyramid = {1: 0, 2: 0, 3: 0}
    for tier_val, n in db.session.query(
        InterventionPlan.tier, func.count(InterventionPlan.id)
    ).filter_by(counselor_id=current_user.id, status='active').group_by(InterventionPlan.tier).all():
        pyramid[tier_val] = pyramid.get(tier_val, 0) + n

    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active'
    ).order_by(Student.last_name).all()

    return render_template('interventions/index.html',
        plans=plans, students=students,
        student_id=student_id, tier=tier, status=status, pyramid=pyramid,
        tiers=InterventionPlan.TIERS, statuses=InterventionPlan.STATUSES)


@interventions_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if request.method == 'POST':
        subject = caseload_student_or_404(request.form.get('student_id'))
        plan = InterventionPlan(
            student_id=subject.id,
            counselor_id=current_user.id,
            tier=int(request.form.get('tier', 1)),
            concern_area=request.form['concern_area'],
            concern_details=request.form.get('concern_details', '').strip(),
            strategy=request.form['strategy'].strip(),
            frequency=request.form.get('frequency', '').strip(),
            duration=request.form.get('duration', '').strip(),
            location=request.form.get('location', '').strip(),
            interventionist=request.form.get('interventionist', '').strip(),
            success_criteria=request.form.get('success_criteria', '').strip(),
            baseline_data=request.form.get('baseline_data', '').strip(),
            start_date=parse_date(request.form.get('start_date')) or date.today(),
            review_date=parse_date(request.form.get('review_date')),
            status=request.form.get('status', 'active'),
        )
        db.session.add(plan)
        db.session.commit()
        log_action('create', 'intervention', plan.id,
                   f'Tier {plan.tier} plan: {plan.concern_area}')
        flash('Intervention plan created.', 'success')
        return redirect(url_for('interventions.view', id=plan.id))

    student_id = request.args.get('student_id', '')
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active'
    ).order_by(Student.last_name).all()
    return render_template('interventions/add.html',
        students=students, preselected_student=student_id,
        tiers=InterventionPlan.TIERS,
        concern_areas=InterventionPlan.CONCERN_AREAS,
        statuses=InterventionPlan.STATUSES)


@interventions_bp.route('/<int:id>')
@login_required
def view(id):
    plan = owned_or_404(InterventionPlan, id)
    log_action('view', 'intervention', plan.id)
    return render_template('interventions/view.html', plan=plan,
        data_sources=InterventionPlan.DATA_SOURCES)


@interventions_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    plan = owned_or_404(InterventionPlan, id)
    if request.method == 'POST':
        plan.tier = int(request.form.get('tier', plan.tier))
        plan.concern_area = request.form['concern_area']
        plan.concern_details = request.form.get('concern_details', '').strip()
        plan.strategy = request.form['strategy'].strip()
        plan.frequency = request.form.get('frequency', '').strip()
        plan.duration = request.form.get('duration', '').strip()
        plan.location = request.form.get('location', '').strip()
        plan.interventionist = request.form.get('interventionist', '').strip()
        plan.success_criteria = request.form.get('success_criteria', '').strip()
        plan.baseline_data = request.form.get('baseline_data', '').strip()
        plan.start_date = parse_date(request.form.get('start_date')) or plan.start_date
        plan.review_date = parse_date(request.form.get('review_date'))
        plan.end_date = parse_date(request.form.get('end_date'))
        plan.status = request.form.get('status', plan.status)
        plan.outcome = request.form.get('outcome', '').strip()
        plan.next_steps = request.form.get('next_steps', '').strip()
        db.session.commit()
        log_action('update', 'intervention', plan.id)
        flash('Plan updated.', 'success')
        return redirect(url_for('interventions.view', id=plan.id))

    return render_template('interventions/edit.html', plan=plan,
        tiers=InterventionPlan.TIERS,
        concern_areas=InterventionPlan.CONCERN_AREAS,
        statuses=InterventionPlan.STATUSES)


@interventions_bp.route('/<int:id>/progress', methods=['POST'])
@login_required
def add_progress(id):
    plan = owned_or_404(InterventionPlan, id)
    entry = InterventionProgress(
        plan_id=plan.id,
        entry_date=parse_date(request.form.get('entry_date')) or date.today(),
        metric_value=request.form.get('metric_value', '').strip(),
        data_source=request.form.get('data_source', ''),
        note=request.form.get('note', '').strip(),
    )
    db.session.add(entry)
    db.session.commit()
    log_action('create', 'intervention_progress', entry.id)
    flash('Progress recorded.', 'success')
    return redirect(url_for('interventions.view', id=plan.id))


@interventions_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    plan = owned_or_404(InterventionPlan, id)
    log_action('delete', 'intervention', plan.id)
    db.session.delete(plan)
    db.session.commit()
    flash('Plan deleted.', 'warning')
    return redirect(url_for('interventions.index'))
