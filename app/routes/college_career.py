"""College & Career Hub — post-secondary planning, applications, test scores, financial aid."""
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models.student import Student
from app.models.college_career import CollegeCareerPlan, CollegeApplication, TestScore
from app.utils.roles import owned_or_404, caseload_student_or_404

college_career_bp = Blueprint('college_career', __name__)


def _owned_plan_child_or_404(model, obj_id):
    """Fetch a CollegeApplication/TestScore scoped to the caller's caseload.

    Neither child carries an owner column — only plan_id — and the parent's
    CollegeCareerPlan.counselor_id is nullable, so it can't be relied on.
    Resolve ownership through the student instead, which is always assigned.
    """
    obj = model.query.get_or_404(obj_id)
    caseload_student_or_404(obj.plan.student_id)
    return obj


def _parse_date(val):
    if not val:
        return None
    try:
        return datetime.strptime(val, '%Y-%m-%d').date()
    except ValueError:
        return None


def _parse_int(val):
    try:
        return int(val) if val else None
    except (ValueError, TypeError):
        return None


def _parse_float(val):
    try:
        return float(val) if val else None
    except (ValueError, TypeError):
        return None


@college_career_bp.route('/')
@login_required
def index():
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active'
    ).order_by(Student.last_name, Student.first_name).all()

    grade_filter = request.args.get('grade', '')
    pathway_filter = request.args.get('pathway', '')
    fafsa_filter = request.args.get('fafsa', '')
    status_filter = request.args.get('status', '')

    rows = []
    stats = {
        'total': 0, 'with_plan': 0, 'no_plan': 0,
        'pathway_counts': {}, 'fafsa_submitted': 0, 'fafsa_total_seniors': 0,
        'apps_submitted': 0, 'apps_total': 0, 'committed': 0,
    }

    for s in students:
        if grade_filter and str(s.grade_level) != grade_filter:
            continue

        plan = s.college_career_plan
        stats['total'] += 1

        if s.grade_level and s.grade_level >= 12:
            stats['fafsa_total_seniors'] += 1

        if not plan:
            if pathway_filter or fafsa_filter or status_filter:
                if pathway_filter == 'no_plan' or (not pathway_filter and not fafsa_filter and not status_filter):
                    pass
                elif pathway_filter != 'no_plan':
                    continue
            stats['no_plan'] += 1
            rows.append({'student': s, 'plan': None})
            continue

        stats['with_plan'] += 1
        pw = plan.pathway or 'undecided'
        stats['pathway_counts'][pw] = stats['pathway_counts'].get(pw, 0) + 1

        if plan.fafsa_status in ('submitted', 'verified') and s.grade_level and s.grade_level >= 12:
            stats['fafsa_submitted'] += 1

        sub = plan.apps_submitted
        tot = plan.apps_total
        stats['apps_submitted'] += sub
        stats['apps_total'] += tot
        if plan.committed_college:
            stats['committed'] += 1

        if pathway_filter and pathway_filter != 'no_plan' and pw != pathway_filter:
            continue
        if pathway_filter == 'no_plan':
            continue
        if fafsa_filter and plan.fafsa_status != fafsa_filter:
            continue
        if status_filter == 'committed' and not plan.committed_college:
            continue
        if status_filter == 'no_apps' and tot > 0:
            continue
        if status_filter == 'has_apps' and tot == 0:
            continue

        rows.append({'student': s, 'plan': plan})

    return render_template('college_career/index.html',
                           rows=rows, stats=stats,
                           grade_filter=grade_filter,
                           pathway_filter=pathway_filter,
                           fafsa_filter=fafsa_filter,
                           status_filter=status_filter,
                           pathways=CollegeCareerPlan.PATHWAYS)


@college_career_bp.route('/student/<int:student_id>')
@login_required
def student_plan(student_id):
    student = owned_or_404(Student, student_id, owner_attr='assigned_counselor_id')
    plan = student.college_career_plan
    if not plan:
        return render_template('college_career/student_plan.html',
                               student=student, plan=None,
                               applications=[], test_scores=[],
                               pathways=CollegeCareerPlan.PATHWAYS)

    applications = plan.applications.all()
    scores = plan.test_scores.all()
    return render_template('college_career/student_plan.html',
                           student=student, plan=plan,
                           applications=applications, test_scores=scores,
                           pathways=CollegeCareerPlan.PATHWAYS)


@college_career_bp.route('/student/<int:student_id>/create', methods=['POST'])
@login_required
def create_plan(student_id):
    student = owned_or_404(Student, student_id, owner_attr='assigned_counselor_id')
    if student.college_career_plan:
        flash('Plan already exists for this student.', 'warning')
        return redirect(url_for('college_career.student_plan', student_id=student_id))

    plan = CollegeCareerPlan(
        student_id=student_id,
        counselor_id=current_user.id,
        pathway='undecided',
    )
    db.session.add(plan)
    db.session.commit()
    flash('College & Career plan created.', 'success')
    return redirect(url_for('college_career.edit_plan', student_id=student_id))


@college_career_bp.route('/student/<int:student_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_plan(student_id):
    student = owned_or_404(Student, student_id, owner_attr='assigned_counselor_id')
    plan = student.college_career_plan
    if not plan:
        flash('No plan exists yet. Create one first.', 'warning')
        return redirect(url_for('college_career.student_plan', student_id=student_id))

    if request.method == 'POST':
        plan.pathway = request.form.get('pathway', 'undecided')
        plan.intended_major = request.form.get('intended_major', '').strip()
        plan.career_interest = request.form.get('career_interest', '').strip()
        plan.gpa_weighted = _parse_float(request.form.get('gpa_weighted'))
        plan.gpa_unweighted = _parse_float(request.form.get('gpa_unweighted'))
        plan.sat_total = _parse_int(request.form.get('sat_total'))
        plan.sat_reading = _parse_int(request.form.get('sat_reading'))
        plan.sat_math = _parse_int(request.form.get('sat_math'))
        plan.act_composite = _parse_int(request.form.get('act_composite'))
        plan.fafsa_status = request.form.get('fafsa_status', 'not_started')
        plan.fafsa_submitted_date = _parse_date(request.form.get('fafsa_submitted_date'))
        plan.css_profile_status = request.form.get('css_profile_status', 'not_needed')
        plan.dream_act_status = request.form.get('dream_act_status', 'not_needed')
        plan.personal_statement_status = request.form.get('personal_statement_status', 'not_started')
        plan.letters_of_rec_requested = _parse_int(request.form.get('letters_of_rec_requested')) or 0
        plan.letters_of_rec_received = _parse_int(request.form.get('letters_of_rec_received')) or 0
        plan.transcript_sent = request.form.get('transcript_sent') == 'on'
        plan.notes = request.form.get('notes', '').strip()
        db.session.commit()
        flash('Plan updated.', 'success')
        return redirect(url_for('college_career.student_plan', student_id=student_id))

    return render_template('college_career/edit.html',
                           student=student, plan=plan,
                           pathways=CollegeCareerPlan.PATHWAYS,
                           fafsa_statuses=CollegeCareerPlan.FAFSA_STATUSES,
                           aid_statuses=CollegeCareerPlan.AID_STATUSES,
                           statement_statuses=CollegeCareerPlan.STATEMENT_STATUSES)


@college_career_bp.route('/student/<int:student_id>/application/add', methods=['GET', 'POST'])
@login_required
def add_application(student_id):
    student = owned_or_404(Student, student_id, owner_attr='assigned_counselor_id')
    plan = student.college_career_plan
    if not plan:
        flash('Create a college plan first.', 'warning')
        return redirect(url_for('college_career.student_plan', student_id=student_id))

    if request.method == 'POST':
        app_record = CollegeApplication(
            plan_id=plan.id,
            college_name=request.form.get('college_name', '').strip(),
            college_type=request.form.get('college_type', ''),
            application_type=request.form.get('application_type', ''),
            status=request.form.get('status', 'planned'),
            deadline=_parse_date(request.form.get('deadline')),
            submitted_date=_parse_date(request.form.get('submitted_date')),
            decision_date=_parse_date(request.form.get('decision_date')),
            financial_aid_offered=_parse_float(request.form.get('financial_aid_offered')),
            notes=request.form.get('notes', '').strip(),
        )
        db.session.add(app_record)
        db.session.commit()
        flash(f'Added {app_record.college_name}.', 'success')
        return redirect(url_for('college_career.student_plan', student_id=student_id))

    return render_template('college_career/add_application.html',
                           student=student, plan=plan,
                           college_types=CollegeApplication.COLLEGE_TYPES,
                           app_types=CollegeApplication.APP_TYPES,
                           statuses=CollegeApplication.STATUSES)


@college_career_bp.route('/application/<int:app_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_application(app_id):
    app_record = _owned_plan_child_or_404(CollegeApplication, app_id)
    plan = app_record.plan
    student = plan.student

    if request.method == 'POST':
        app_record.college_name = request.form.get('college_name', '').strip()
        app_record.college_type = request.form.get('college_type', '')
        app_record.application_type = request.form.get('application_type', '')
        app_record.status = request.form.get('status', 'planned')
        app_record.deadline = _parse_date(request.form.get('deadline'))
        app_record.submitted_date = _parse_date(request.form.get('submitted_date'))
        app_record.decision_date = _parse_date(request.form.get('decision_date'))
        app_record.financial_aid_offered = _parse_float(request.form.get('financial_aid_offered'))
        app_record.notes = request.form.get('notes', '').strip()
        db.session.commit()
        flash(f'Updated {app_record.college_name}.', 'success')
        return redirect(url_for('college_career.student_plan', student_id=student.id))

    return render_template('college_career/add_application.html',
                           student=student, plan=plan,
                           app_record=app_record,
                           college_types=CollegeApplication.COLLEGE_TYPES,
                           app_types=CollegeApplication.APP_TYPES,
                           statuses=CollegeApplication.STATUSES)


@college_career_bp.route('/application/<int:app_id>/delete', methods=['POST'])
@login_required
def delete_application(app_id):
    app_record = _owned_plan_child_or_404(CollegeApplication, app_id)
    student_id = app_record.plan.student_id
    name = app_record.college_name
    db.session.delete(app_record)
    db.session.commit()
    flash(f'Removed {name}.', 'success')
    return redirect(url_for('college_career.student_plan', student_id=student_id))


@college_career_bp.route('/student/<int:student_id>/test/add', methods=['GET', 'POST'])
@login_required
def add_test(student_id):
    student = owned_or_404(Student, student_id, owner_attr='assigned_counselor_id')
    plan = student.college_career_plan
    if not plan:
        flash('Create a college plan first.', 'warning')
        return redirect(url_for('college_career.student_plan', student_id=student_id))

    if request.method == 'POST':
        score = TestScore(
            plan_id=plan.id,
            test_type=request.form.get('test_type', 'sat'),
            test_name=request.form.get('test_name', '').strip(),
            test_date=_parse_date(request.form.get('test_date')),
            score=request.form.get('score', '').strip(),
            score_detail=request.form.get('score_detail', '').strip(),
        )
        db.session.add(score)
        db.session.commit()
        flash(f'Added {score.display_name} score.', 'success')
        return redirect(url_for('college_career.student_plan', student_id=student_id))

    return render_template('college_career/add_test.html',
                           student=student, plan=plan,
                           test_types=TestScore.TEST_TYPES)


@college_career_bp.route('/test/<int:test_id>/delete', methods=['POST'])
@login_required
def delete_test(test_id):
    score = _owned_plan_child_or_404(TestScore, test_id)
    student_id = score.plan.student_id
    db.session.delete(score)
    db.session.commit()
    flash('Test score removed.', 'success')
    return redirect(url_for('college_career.student_plan', student_id=student_id))
