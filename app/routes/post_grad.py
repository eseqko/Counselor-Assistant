from collections import Counter
from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_login import login_required, current_user
from app import db, csrf
from app.models.post_grad import PostGradOutcome
from app.models.student import Student
from app.utils.audit import log_action
from app.utils.helpers import parse_date
from app.utils.roles import caseload_student_or_404, owned_or_404

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

    # Eligible graduates without outcomes — each gets a shareable self-report
    # link so a whole graduating cohort can be surveyed in one pass through
    # this list. Token generation is idempotent (safe to recompute every view).
    grads_without = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='graduated'
    ).outerjoin(PostGradOutcome).filter(PostGradOutcome.id.is_(None)).all()
    grads_without_links = [
        (s, url_for('post_grad.public_survey',
                    token=s.get_or_create_postgrad_token(), _external=True))
        for s in grads_without
    ]

    return render_template('post_grad/index.html',
        outcomes=outcomes, pathway_counts=dict(pathway_counts),
        year_counts=dict(year_counts), years=years,
        grad_year=grad_year, pathway=pathway,
        pathways=PostGradOutcome.PATHWAYS,
        grads_without=grads_without,
        grads_without_links=grads_without_links)


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


@post_grad_bp.route('/survey-link/<int:student_id>', methods=['POST'])
@csrf.exempt
@login_required
def survey_link(student_id):
    """AJAX: mint (or fetch) a student's self-report link on demand.

    Used by add.html, where the target student is chosen client-side from a
    dropdown, so no concrete student is known until the page already loaded —
    unlike index.html/edit.html, which know the student up front and can just
    render the link server-side.
    """
    student = caseload_student_or_404(student_id)
    token = student.get_or_create_postgrad_token()
    url = url_for('post_grad.public_survey', token=token, _external=True)
    return jsonify({'ok': True, 'url': url, 'student_email': student.email or ''})


@post_grad_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    # Ownership-scoped: this route now also mints/reveals the student's
    # public survey link, so an unscoped get_or_404 here would let one
    # counselor read (and generate a working share link for) another
    # counselor's student — tightened alongside adding that link.
    outcome = owned_or_404(PostGradOutcome, id)
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

    survey_url = url_for('post_grad.public_survey',
        token=outcome.student.get_or_create_postgrad_token(), _external=True)
    return render_template('post_grad/edit.html', outcome=outcome,
        pathways=PostGradOutcome.PATHWAYS,
        statuses=PostGradOutcome.STATUSES,
        survey_url=survey_url)


@post_grad_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    outcome = owned_or_404(PostGradOutcome, id)
    log_action('delete', 'post_grad_outcome', outcome.id)
    db.session.delete(outcome)
    db.session.commit()
    flash('Outcome deleted.', 'warning')
    return redirect(url_for('post_grad.index'))


# =====================================================================
#  PUBLIC SELF-REPORT SURVEY (no login — alumni fill this in themselves)
# =====================================================================
#
# Security model: the token is the ONLY way this public route learns which
# student a submission belongs to. student_id is never read from the form —
# doing so would let anyone rewrite ANY student's outcome by simply changing
# a hidden field. 404 (not a friendlier error) on an invalid token, matching
# the app-wide convention of never confirming a record's existence to an
# unauthenticated caller.

def _survey_student_or_404(token):
    student = Student.query.filter_by(postgrad_survey_token=token).first()
    if not student:
        abort(404)
    return student


@post_grad_bp.route('/survey/<token>')
def public_survey(token):
    """Public self-report form — what a graduate sees when they open the link."""
    student = _survey_student_or_404(token)
    existing = PostGradOutcome.query.filter_by(student_id=student.id).first()
    return render_template('post_grad/survey.html',
        student=student, existing=existing, pathways=PostGradOutcome.PATHWAYS,
        submitted=False, error=None)


@post_grad_bp.route('/survey/<token>', methods=['POST'])
@csrf.exempt
def public_survey_submit(token):
    student = _survey_student_or_404(token)
    existing = PostGradOutcome.query.filter_by(student_id=student.id).first()

    if not student.assigned_counselor_id:
        # Student has no counselor right now (e.g. unassigned in a caseload
        # sync) — nowhere safe to attribute a new record. Rare edge case;
        # fail with a human message rather than guessing an owner.
        return render_template('post_grad/survey.html',
            student=student, existing=existing, pathways=PostGradOutcome.PATHWAYS,
            submitted=False,
            error="We couldn't find your counselor for this link right now — "
                 'please reach out to your school directly.'), 400

    pathway = request.form.get('primary_pathway', '').strip()
    if pathway not in {v for v, _ in PostGradOutcome.PATHWAYS}:
        return render_template('post_grad/survey.html',
            student=student, existing=existing, pathways=PostGradOutcome.PATHWAYS,
            submitted=False,
            error='Please choose what best describes what you are doing now.'), 400

    is_new = existing is None
    outcome = existing or PostGradOutcome(student_id=student.id)
    # Always the student's CURRENT counselor — never client-supplied, and
    # re-derived on every submission so a re-assigned student's update lands
    # with their present counselor rather than a stale one.
    outcome.counselor_id = student.assigned_counselor_id
    outcome.primary_pathway = pathway
    grad_year_raw = request.form.get('graduation_year', '').strip()
    if grad_year_raw.isdigit():
        outcome.graduation_year = int(grad_year_raw)
    outcome.institution_name = request.form.get('institution_name', '').strip()
    outcome.program_major = request.form.get('program_major', '').strip()
    outcome.job_title = request.form.get('job_title', '').strip()
    outcome.employer = request.form.get('employer', '').strip()
    outcome.military_branch = request.form.get('military_branch', '').strip()
    outcome.contact_email = request.form.get('contact_email', '').strip()
    outcome.contact_phone = request.form.get('contact_phone', '').strip()
    outcome.notes = request.form.get('notes', '').strip()
    outcome.last_followup_date = date.today()

    if is_new:
        db.session.add(outcome)
    db.session.commit()
    log_action('create' if is_new else 'update', 'post_grad_outcome', outcome.id,
              details='self-reported via public survey link')

    return render_template('post_grad/survey.html',
        student=student, existing=outcome, pathways=PostGradOutcome.PATHWAYS,
        submitted=True, error=None)
