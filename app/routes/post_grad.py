from collections import Counter
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models.post_grad import PostGradOutcome
from app.models.student import Student
from app.utils.audit import log_action
from app.utils.helpers import parse_date
from app.utils.roles import caseload_student_or_404

post_grad_bp = Blueprint('post_grad', __name__)


@post_grad_bp.route('/')
@login_required
def index():
    grad_year = request.args.get('grad_year', '')
    pathway = request.args.get('pathway', '')

    query = PostGradOutcome.query.filter_by(counselor_id=current_user.id)
    if grad_year:
        query = query.filter_by(graduation_year=int(grad_year))
    if pathway:
        query = query.filter_by(primary_pathway=pathway)

    outcomes = query.order_by(PostGradOutcome.graduation_year.desc()).all()

    # Aggregates
    pathway_counts = Counter(o.primary_pathway for o in outcomes)
    year_counts = Counter(o.graduation_year for o in outcomes if o.graduation_year)

    all_outcomes = PostGradOutcome.query.filter_by(counselor_id=current_user.id).all()
    years = sorted({o.graduation_year for o in all_outcomes if o.graduation_year}, reverse=True)

    # Eligible graduates without outcomes
    grads_without = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='graduated'
    ).outerjoin(PostGradOutcome).filter(PostGradOutcome.id.is_(None)).all()

    return render_template('post_grad/index.html',
        outcomes=outcomes, pathway_counts=dict(pathway_counts),
        year_counts=dict(year_counts), years=years,
        grad_year=grad_year, pathway=pathway,
        pathways=PostGradOutcome.PATHWAYS,
        grads_without=grads_without)


@post_grad_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if request.method == 'POST':
        student_id = caseload_student_or_404(request.form.get('student_id')).id
        existing = PostGradOutcome.query.filter_by(student_id=student_id).first()
        if existing:
            flash('That student already has a post-grad record. Edit instead.', 'warning')
            return redirect(url_for('post_grad.edit', id=existing.id))

        outcome = PostGradOutcome(
            student_id=student_id,
            counselor_id=current_user.id,
            graduation_year=int(request.form['graduation_year']) if request.form.get('graduation_year') else None,
            graduation_date=parse_date(request.form.get('graduation_date')),
            primary_pathway=request.form['primary_pathway'],
            institution_name=request.form.get('institution_name', '').strip(),
            program_major=request.form.get('program_major', '').strip(),
            job_title=request.form.get('job_title', '').strip(),
            employer=request.form.get('employer', '').strip(),
            military_branch=request.form.get('military_branch', '').strip(),
            contact_email=request.form.get('contact_email', '').strip(),
            contact_phone=request.form.get('contact_phone', '').strip(),
            notes=request.form.get('notes', '').strip(),
        )
        db.session.add(outcome)
        db.session.commit()
        log_action('create', 'post_grad_outcome', outcome.id)
        flash('Post-grad outcome recorded.', 'success')
        return redirect(url_for('post_grad.index'))

    student_id = request.args.get('student_id', '')
    grads = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='graduated'
    ).order_by(Student.last_name).all()
    return render_template('post_grad/add.html',
        grads=grads, preselected_student=student_id,
        pathways=PostGradOutcome.PATHWAYS)


@post_grad_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    outcome = PostGradOutcome.query.get_or_404(id)
    if request.method == 'POST':
        outcome.graduation_year = int(request.form['graduation_year']) if request.form.get('graduation_year') else None
        outcome.graduation_date = parse_date(request.form.get('graduation_date'))
        outcome.primary_pathway = request.form['primary_pathway']
        outcome.institution_name = request.form.get('institution_name', '').strip()
        outcome.program_major = request.form.get('program_major', '').strip()
        outcome.job_title = request.form.get('job_title', '').strip()
        outcome.employer = request.form.get('employer', '').strip()
        outcome.military_branch = request.form.get('military_branch', '').strip()
        outcome.status_at_6mo = request.form.get('status_at_6mo', '')
        outcome.status_at_1yr = request.form.get('status_at_1yr', '')
        outcome.status_at_2yr = request.form.get('status_at_2yr', '')
        outcome.enrollment_verified = 'enrollment_verified' in request.form
        outcome.completed_credential = 'completed_credential' in request.form
        outcome.contact_email = request.form.get('contact_email', '').strip()
        outcome.contact_phone = request.form.get('contact_phone', '').strip()
        outcome.last_followup_date = parse_date(request.form.get('last_followup_date'))
        outcome.notes = request.form.get('notes', '').strip()
        db.session.commit()
        log_action('update', 'post_grad_outcome', outcome.id)
        flash('Post-grad outcome updated.', 'success')
        return redirect(url_for('post_grad.index'))

    return render_template('post_grad/edit.html', outcome=outcome,
        pathways=PostGradOutcome.PATHWAYS,
        statuses=PostGradOutcome.STATUSES)


@post_grad_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    outcome = PostGradOutcome.query.get_or_404(id)
    log_action('delete', 'post_grad_outcome', outcome.id)
    db.session.delete(outcome)
    db.session.commit()
    flash('Outcome deleted.', 'warning')
    return redirect(url_for('post_grad.index'))
