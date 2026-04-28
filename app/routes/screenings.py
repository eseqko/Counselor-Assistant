import json
from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models.screening import (ScreeningTemplate, ScreeningResult, BUILTIN_SCREENERS)
from app.models.student import Student
from app.utils.audit import log_action
from app.utils.helpers import parse_date

screenings_bp = Blueprint('screenings', __name__)


def _ensure_builtin_templates():
    """Create built-in screening templates for the current user if missing."""
    for key, defn in BUILTIN_SCREENERS.items():
        existing = ScreeningTemplate.query.filter_by(
            counselor_id=current_user.id, short_name=defn['short_name']
        ).first()
        if existing:
            continue
        # Build full questions with options inline
        opts = defn.get('options', [])
        questions = []
        for q in defn['questions']:
            qcopy = dict(q)
            qcopy['options'] = opts
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
    """Compute score, severity, and interpretation."""
    total = 0
    for v in responses.values():
        try:
            total += int(v)
        except (ValueError, TypeError):
            pass

    severity = ''
    interpretation = ''
    scoring = template.scoring or {}
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

    return render_template('screenings/index.html',
        templates=templates, results=results, students=students,
        student_id=student_id)


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

        result = ScreeningResult(
            template_id=template.id,
            student_id=int(request.form['student_id']),
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
    result = ScreeningResult.query.get_or_404(id)
    log_action('view', 'screening_result', result.id)
    return render_template('screenings/view_result.html', result=result,
        questions=result.template.questions, responses=result.responses)


@screenings_bp.route('/result/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_result(id):
    result = ScreeningResult.query.get_or_404(id)
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
    result = ScreeningResult.query.get_or_404(id)
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
