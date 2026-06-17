import json
from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models.screening import (ScreeningTemplate, ScreeningResult, BUILTIN_SCREENERS)
from app.models.student import Student
from app.utils.audit import log_action
from app.utils.helpers import parse_date
from app.utils.google_client import is_connected
from app.utils.roles import owned_or_404
from app.utils.caseload import caseload_student_ids

screenings_bp = Blueprint('screenings', __name__)


def _ensure_builtin_templates():
    """Create built-in screening templates for the current user if missing."""
    for key, defn in BUILTIN_SCREENERS.items():
        existing = ScreeningTemplate.query.filter_by(
            counselor_id=current_user.id, short_name=defn['short_name']
        ).first()
        if existing:
            continue
        shared_opts = defn.get('options', [])
        questions = []
        for q in defn['questions']:
            qcopy = dict(q)
            if 'options' not in qcopy:
                qcopy['options'] = shared_opts
            questions.append(qcopy)
        tpl = ScreeningTemplate(
            counselor_id=current_user.id,
            name=defn['name'],
            short_name=defn['short_name'],
            description=defn['description'],
            instructions=defn['instructions'],
            questions_json=json.dumps(questions),
            scoring_json=json.dumps(defn['scoring']),
            is_built_in=True,
        )
        db.session.add(tpl)
    db.session.commit()


def _calc_score(template, responses):
    """Compute score, severity, and interpretation.

    Supports two scoring types:
    - 'sum' (default): sum all responses → match to severity range
    - 'dimensions': group responses by question dimension, rank dimensions
    """
    scoring = template.scoring or {}
    scoring_type = scoring.get('type', 'sum')

    if scoring_type == 'dimensions':
        return _calc_dimension_score(template, responses, scoring)
    if scoring_type == 'personality':
        return _calc_personality_score(template, responses, scoring)

    total = 0
    for v in responses.values():
        try:
            total += int(v)
        except (ValueError, TypeError):
            pass

    severity = ''
    interpretation = ''
    for r in scoring.get('ranges', []):
        if r['min'] <= total <= r['max']:
            severity = r['label']
            interpretation = r.get('action', '')
            break

    flag_q = scoring.get('flag_question')
    if flag_q:
        flag_val = responses.get(flag_q, 0)
        try:
            flag_val = int(flag_val)
        except (ValueError, TypeError):
            flag_val = 0
        if flag_val > 0:
            interpretation = (interpretation + ' [SAFETY FLAG: critical item endorsed.]').strip()

    return total, severity, interpretation


def _calc_dimension_score(template, responses, scoring):
    """Score a multi-dimension assessment (e.g. RIASEC)."""
    questions = template.questions
    dim_scores = {}
    for q in questions:
        dim = q.get('dimension', 'general')
        val = responses.get(q['id'], 0)
        try:
            val = int(val)
        except (ValueError, TypeError):
            val = 0
        dim_scores[dim] = dim_scores.get(dim, 0) + val

    dim_order = scoring.get('dimensions', sorted(dim_scores.keys()))
    ranked = sorted(dim_order, key=lambda d: dim_scores.get(d, 0), reverse=True)

    profile_code = ''.join(
        scoring.get('dimension_codes', {}).get(d, d[0].upper()) for d in ranked[:3]
    )

    top_score = dim_scores.get(ranked[0], 0) if ranked else 0

    lines = []
    dim_labels = scoring.get('dimension_labels', {})
    for d in ranked:
        label = dim_labels.get(d, d)
        lines.append(f'{label}: {dim_scores.get(d, 0)}')
    interpretation = ' | '.join(lines)

    return top_score, profile_code, interpretation


def _calc_personality_score(template, responses, scoring):
    """Score a personality type assessment (e.g. Jungian E/I, S/N, T/F, J/P)."""
    axes = scoring.get('axes', [])
    questions = template.questions

    axis_sums = {}
    axis_counts = {}
    for q in questions:
        dim = q.get('dimension', '')
        val = responses.get(q['id'], 0)
        try:
            val = int(val)
        except (ValueError, TypeError):
            val = 0
        axis_sums[dim] = axis_sums.get(dim, 0) + val
        axis_counts[dim] = axis_counts.get(dim, 0) + 1

    type_code = ''
    parts = []
    for axis in axes:
        aid = axis['id']
        total = axis_sums.get(aid, 0)
        count = axis_counts.get(aid, 1)
        threshold = count / 2
        if total >= threshold:
            type_code += axis['pole_b']
            parts.append(f"{axis['label_b']} ({axis['pole_b']})")
        else:
            type_code += axis['pole_a']
            parts.append(f"{axis['label_a']} ({axis['pole_a']})")

    interpretation = ', '.join(parts)
    return 0, type_code, interpretation


@screenings_bp.route('/')
@login_required
def index():
    _ensure_builtin_templates()
    templates = ScreeningTemplate.query.filter_by(
        counselor_id=current_user.id, is_active=True
    ).order_by(ScreeningTemplate.is_built_in.desc(), ScreeningTemplate.name).all()

    student_id = request.args.get('student_id', '')
    query = ScreeningResult.query.filter_by(counselor_id=current_user.id)
    if student_id:
        query = query.filter_by(student_id=int(student_id))
    results = query.order_by(ScreeningResult.administered_date.desc()).limit(50).all()

    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active'
    ).order_by(Student.last_name).all()

    google_connected = is_connected(current_user)
    return render_template('screenings/index.html',
        templates=templates, results=results, students=students,
        student_id=student_id, google_connected=google_connected)


@screenings_bp.route('/template/<int:tid>/administer', methods=['GET', 'POST'])
@login_required
def administer(tid):
    template = ScreeningTemplate.query.get_or_404(tid)
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active'
    ).order_by(Student.last_name).all()

    if request.method == 'POST':
        responses = {}
        for q in template.questions:
            val = request.form.get(q['id'])
            if val is not None:
                responses[q['id']] = val

        total, severity, interp = _calc_score(template, responses)

        # Validate the posted student_id is on this counselor's caseload before
        # binding a result to it — blocks administering (and later viewing) a
        # screening against a foreign or shadow student id.
        subject = owned_or_404(Student, int(request.form['student_id']),
                               owner_attr='assigned_counselor_id')

        result = ScreeningResult(
            template_id=template.id,
            student_id=subject.id,
            counselor_id=current_user.id,
            administered_date=parse_date(request.form.get('administered_date')) or date.today(),
            responses_json=json.dumps(responses),
            total_score=total,
            severity=severity,
            interpretation=interp,
            notes=request.form.get('notes', '').strip(),
        )
        db.session.add(result)
        db.session.commit()
        log_action('create', 'screening_result', result.id,
                   f'{template.short_name}: {severity} ({total})')
        flash(f'Screening recorded. Score: {total} ({severity})', 'success')
        return redirect(url_for('screenings.view_result', id=result.id))

    student_id = request.args.get('student_id', '')
    return render_template('screenings/administer.html',
        template=template, students=students, preselected_student=student_id)


@screenings_bp.route('/result/<int:id>')
@login_required
def view_result(id):
    result = owned_or_404(ScreeningResult, id, owner_attr='counselor_id')
    log_action('view', 'screening_result', result.id)
    return render_template('screenings/view_result.html', result=result,
        questions=result.template.questions, responses=result.responses)


@screenings_bp.route('/result/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_result(id):
    result = owned_or_404(ScreeningResult, id, owner_attr='counselor_id')
    if request.method == 'POST':
        result.notes = request.form.get('notes', '').strip()
        result.action_taken = request.form.get('action_taken', '').strip()
        db.session.commit()
        log_action('update', 'screening_result', result.id)
        flash('Screening updated.', 'success')
        return redirect(url_for('screenings.view_result', id=result.id))
    return render_template('screenings/edit_result.html', result=result)


@screenings_bp.route('/result/<int:id>/delete', methods=['POST'])
@login_required
def delete_result(id):
    result = owned_or_404(ScreeningResult, id, owner_attr='counselor_id')
    log_action('delete', 'screening_result', result.id)
    db.session.delete(result)
    db.session.commit()
    flash('Result deleted.', 'warning')
    return redirect(url_for('screenings.index'))


@screenings_bp.route('/template/add', methods=['GET', 'POST'])
@login_required
def add_template():
    if request.method == 'POST':
        # Build questions from form
        questions = []
        q_texts = request.form.getlist('q_text')
        for i, text in enumerate(q_texts):
            text = text.strip()
            if not text:
                continue
            questions.append({
                'id': f'q{i+1}',
                'text': text,
                'options': [
                    {'label': 'Not at all', 'value': 0},
                    {'label': 'Several days', 'value': 1},
                    {'label': 'More than half the days', 'value': 2},
                    {'label': 'Nearly every day', 'value': 3},
                ],
            })

        tpl = ScreeningTemplate(
            counselor_id=current_user.id,
            name=request.form['name'].strip(),
            short_name=request.form.get('short_name', '').strip(),
            description=request.form.get('description', '').strip(),
            instructions=request.form.get('instructions', '').strip(),
            questions_json=json.dumps(questions),
            scoring_json='{}',
        )
        db.session.add(tpl)
        db.session.commit()
        log_action('create', 'screening_template', tpl.id)
        flash('Template created.', 'success')
        return redirect(url_for('screenings.index'))
    return render_template('screenings/add_template.html')


@screenings_bp.route('/template/<int:tid>/create-form', methods=['POST'])
@login_required
def create_google_form(tid):
    """Create a Google Form from a screening template."""
    template = ScreeningTemplate.query.get_or_404(tid)

    if not is_connected(current_user):
        flash('Connect your Google account first (Settings → Google).', 'warning')
        return redirect(url_for('screenings.index'))

    from app.utils.google_forms import create_form_from_template
    form_id, form_url = create_form_from_template(current_user, template)

    if not form_id:
        flash('Failed to create Google Form. You may need to re-authorize with '
              'the new Forms scope — go to Settings → Google → Reconnect.', 'danger')
        return redirect(url_for('screenings.index'))

    template.google_form_id = form_id
    template.google_form_url = form_url
    db.session.commit()

    log_action('create', 'google_form', template.id, f'Form for {template.short_name}')
    flash(f'Google Form created for {template.short_name}!', 'success')
    return redirect(url_for('screenings.manage_form', tid=template.id))


@screenings_bp.route('/template/<int:tid>/form')
@login_required
def manage_form(tid):
    """Manage Google Form for a screening template — share link, post to Classroom."""
    template = ScreeningTemplate.query.get_or_404(tid)

    if not template.google_form_id:
        flash('No Google Form created yet for this template.', 'info')
        return redirect(url_for('screenings.index'))

    courses = []
    google_connected = is_connected(current_user)
    if google_connected:
        try:
            from app.utils.google_classroom import list_courses
            courses = list_courses(current_user)
        except Exception:
            pass

    return render_template('screenings/manage_form.html',
        template=template, courses=courses, google_connected=google_connected)


@screenings_bp.route('/template/<int:tid>/post-classroom', methods=['POST'])
@login_required
def post_to_classroom(tid):
    """Post a screening form link to a Google Classroom course."""
    template = ScreeningTemplate.query.get_or_404(tid)

    if not template.google_form_url:
        flash('Create the Google Form first.', 'warning')
        return redirect(url_for('screenings.index'))

    course_id = request.form.get('course_id')
    post_type = request.form.get('post_type', 'assignment')

    if not course_id:
        flash('Please select a course.', 'warning')
        return redirect(url_for('screenings.manage_form', tid=template.id))

    from app.utils.google_classroom import post_form_to_course, post_announcement_to_course

    desc = template.description or f'Please complete the {template.name} assessment.'
    if template.instructions:
        desc += f'\n\nInstructions: {template.instructions}'

    if post_type == 'announcement':
        result = post_announcement_to_course(
            current_user, course_id,
            f'Please complete: {template.name}\n\n{desc}',
            template.google_form_url,
        )
    else:
        result = post_form_to_course(
            current_user, course_id,
            template.name, desc, template.google_form_url,
        )

    if result:
        log_action('create', 'classroom_post', template.id,
                   f'{template.short_name} → Classroom')
        flash(f'{template.short_name} posted to Google Classroom!', 'success')
    else:
        flash('Failed to post to Classroom. Check your permissions and try again.', 'danger')

    return redirect(url_for('screenings.manage_form', tid=template.id))


@screenings_bp.route('/template/<int:tid>/import-responses')
@login_required
def import_form_responses(tid):
    """Preview responses from Google Form for assignment to students."""
    template = ScreeningTemplate.query.get_or_404(tid)

    if not template.google_form_id:
        flash('No Google Form linked to this template.', 'warning')
        return redirect(url_for('screenings.index'))

    from app.utils.google_forms import get_form_responses, match_responses_to_template

    raw_responses = get_form_responses(current_user, template.google_form_id)
    if not raw_responses:
        flash('No responses found in the Google Form yet.', 'info')
        return redirect(url_for('screenings.manage_form', tid=template.id))

    matched = match_responses_to_template(template, raw_responses)

    existing_ids = set()
    for r in ScreeningResult.query.filter_by(
        template_id=template.id, counselor_id=current_user.id
    ).filter(ScreeningResult.notes.like('gform_resp_%')).all():
        existing_ids.add(r.notes)

    previews = []
    for resp in matched:
        resp_id = resp.get('_response_id', '')
        marker = f'gform_resp_{resp_id}'
        if marker in existing_ids:
            continue

        clean = {k: v for k, v in resp.items() if not k.startswith('_')}
        if not clean:
            continue

        total, severity, interp = _calc_score(template, clean)
        previews.append({
            'response_id': resp_id,
            'submitted': resp.get('_submitted', ''),
            'total': total,
            'severity': severity,
            'interpretation': interp,
            'responses_json': json.dumps(clean),
        })

    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active'
    ).order_by(Student.last_name).all()

    return render_template('screenings/import_responses.html',
        template=template, previews=previews, students=students)


@screenings_bp.route('/template/<int:tid>/save-imports', methods=['POST'])
@login_required
def save_imported_responses(tid):
    """Save imported form responses after student assignment."""
    template = ScreeningTemplate.query.get_or_404(tid)

    response_ids = request.form.getlist('response_id')
    imported = 0
    # Only allow binding imported responses to caseload students — skip any
    # foreign or shadow student id posted in the form.
    caseload_ids = set(caseload_student_ids(current_user))

    for resp_id in response_ids:
        student_id = request.form.get(f'student_{resp_id}')
        if not student_id:
            continue
        try:
            if int(student_id) not in caseload_ids:
                continue
        except (TypeError, ValueError):
            continue

        marker = f'gform_resp_{resp_id}'
        existing = ScreeningResult.query.filter_by(
            template_id=template.id, counselor_id=current_user.id,
            notes=marker
        ).first()
        if existing:
            continue

        responses_json = request.form.get(f'responses_{resp_id}', '{}')
        try:
            clean = json.loads(responses_json)
        except (json.JSONDecodeError, TypeError):
            continue

        total, severity, interp = _calc_score(template, clean)

        result = ScreeningResult(
            template_id=template.id,
            student_id=int(student_id),
            counselor_id=current_user.id,
            administered_date=date.today(),
            responses_json=responses_json,
            total_score=total,
            severity=severity,
            interpretation=interp,
            notes=marker,
        )
        db.session.add(result)
        imported += 1

    db.session.commit()

    if imported:
        log_action('import', 'screening_responses', template.id,
                   f'Imported {imported} from Google Form')
        flash(f'Imported {imported} response(s) and scored.', 'success')
    else:
        flash('No new responses to import.', 'info')

    return redirect(url_for('screenings.manage_form', tid=template.id))
