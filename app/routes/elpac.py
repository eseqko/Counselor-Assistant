"""Manual CRUD for ELPAC scores.

Bulk import via Ellevation CSV lives in app.routes.data_import.elpac.
"""
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from app import db
from app.models.student import Student
from app.models.elpac import ELPACScore
from app.utils.audit import log_action
from app.utils.caseload import caseload_student_ids

elpac_bp = Blueprint('elpac', __name__, template_folder='../templates')


def _own_student_or_404(student_id):
    student = Student.query.get_or_404(student_id)
    if student.id not in caseload_student_ids(current_user):
        abort(404)
    return student


def _own_score_or_404(score_id):
    score = ELPACScore.query.get_or_404(score_id)
    if score.student_id not in caseload_student_ids(current_user):
        abort(404)
    return score


def _parse_int(val):
    if val is None or str(val).strip() == '':
        return None
    try:
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return None


def _parse_date(val):
    if not val:
        return None
    val = str(val).strip()
    for fmt in ('%Y-%m-%d', '%m/%d/%Y'):
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            continue
    return None


def _derive_school_year(d):
    if not d:
        return None
    return f"{d.year}-{d.year + 1}" if d.month >= 7 else f"{d.year - 1}-{d.year}"


def _populate_from_form(score, form):
    """Read form fields onto an ELPACScore (used for both add + edit)."""
    score.test_id = form.get('test_id', '').strip() or None
    score.test_purpose = form.get('test_purpose', 'Summative').strip() or 'Summative'
    score.test_date = _parse_date(form.get('test_date'))
    score.test_grade_level = _parse_int(form.get('test_grade_level'))
    score.test_cluster = form.get('test_cluster', '').strip() or None
    score.test_administrator = form.get('test_administrator', '').strip() or None
    score.school_year = _derive_school_year(score.test_date)

    for prefix in ('listening', 'speaking', 'reading', 'writing',
                   'literacy', 'oral', 'comprehension', 'overall', 'acpl'):
        setattr(score, f'{prefix}_scale', _parse_int(form.get(f'{prefix}_scale')))
        setattr(score, f'{prefix}_level', _parse_int(form.get(f'{prefix}_level')))


@elpac_bp.route('/student/<int:student_id>/add', methods=['GET', 'POST'])
@login_required
def add(student_id):
    student = _own_student_or_404(student_id)

    if request.method == 'POST':
        score = ELPACScore(
            student_id=student.id,
            imported_by_id=current_user.id,
        )
        _populate_from_form(score, request.form)
        if not score.test_date:
            flash('Test date is required.', 'danger')
            return render_template('elpac/form.html', student=student,
                                   score=score, model=ELPACScore)
        db.session.add(score)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash('A test on that date already exists for this student.', 'danger')
            return render_template('elpac/form.html', student=student,
                                   score=score, model=ELPACScore)
        log_action('create', 'elpac_score',
                   details=f'Added ELPAC for student {student.id} on {score.test_date}')
        flash('ELPAC score saved.', 'success')
        return redirect(url_for('caseload.view_student', id=student.id))

    return render_template('elpac/form.html', student=student,
                           score=ELPACScore(), model=ELPACScore)


@elpac_bp.route('/<int:score_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(score_id):
    score = _own_score_or_404(score_id)
    student = score.student

    if request.method == 'POST':
        _populate_from_form(score, request.form)
        if not score.test_date:
            flash('Test date is required.', 'danger')
            return render_template('elpac/form.html', student=student,
                                   score=score, model=ELPACScore)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash('A test on that date already exists for this student.', 'danger')
            return render_template('elpac/form.html', student=student,
                                   score=score, model=ELPACScore)
        log_action('update', 'elpac_score',
                   details=f'Edited ELPAC #{score.id} for student {student.id}')
        flash('ELPAC score updated.', 'success')
        return redirect(url_for('caseload.view_student', id=student.id))

    return render_template('elpac/form.html', student=student,
                           score=score, model=ELPACScore)


@elpac_bp.route('/<int:score_id>/delete', methods=['POST'])
@login_required
def delete(score_id):
    score = _own_score_or_404(score_id)
    student_id = score.student_id
    db.session.delete(score)
    db.session.commit()
    log_action('delete', 'elpac_score',
               details=f'Deleted ELPAC #{score_id} for student {student_id}')
    flash('ELPAC score deleted.', 'success')
    return redirect(url_for('caseload.view_student', id=student_id))
