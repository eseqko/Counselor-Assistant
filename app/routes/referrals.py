from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.referral import Referral
from app.models.student import Student
from app.utils.audit import log_action
from app.utils.helpers import parse_date
from app.utils.roles import owned_or_404, caseload_student_or_404

referrals_bp = Blueprint('referrals', __name__)


@referrals_bp.route('/')
@login_required
def index():
    student_id = request.args.get('student_id', '')
    status = request.args.get('status', '')
    urgency = request.args.get('urgency', '')
    referral_type = request.args.get('referral_type', '')

    query = Referral.query.filter_by(counselor_id=current_user.id)
    if student_id:
        query = query.filter_by(student_id=int(student_id))
    if status:
        if status == 'open':
            query = query.filter(Referral.status.in_(['pending', 'contacted', 'in_progress']))
        else:
            query = query.filter_by(status=status)
    if urgency:
        query = query.filter_by(urgency=urgency)
    if referral_type:
        query = query.filter_by(referral_type=referral_type)

    page = request.args.get('page', 1, type=int)
    pagination = query.order_by(Referral.referral_date.desc()).paginate(
        page=max(1, page), per_page=50, error_out=False)
    referrals = pagination.items
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active'
    ).order_by(Student.last_name).all()

    # Counts by status for the summary bar (one grouped query instead of loading all rows)
    from sqlalchemy import func
    count_rows = db.session.query(
        Referral.status, func.count(Referral.id)
    ).filter_by(counselor_id=current_user.id).group_by(Referral.status).all()
    counts = {s: 0 for s, _ in Referral.STATUSES}
    counts['open'] = 0
    for status, n in count_rows:
        counts[status] = counts.get(status, 0) + n
        if status in ('pending', 'contacted', 'in_progress'):
            counts['open'] += n

    return render_template('referrals/index.html',
        referrals=referrals, pagination=pagination, students=students,
        student_id=student_id, status=status, urgency=urgency, referral_type=referral_type,
        statuses=Referral.STATUSES, urgency_levels=Referral.URGENCY_LEVELS,
        referral_types=Referral.REFERRAL_TYPES, counts=counts)


@referrals_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if request.method == 'POST':
        subject = caseload_student_or_404(request.form.get('student_id'))
        ref = Referral(
            student_id=subject.id,
            counselor_id=current_user.id,
            referral_date=parse_date(request.form.get('referral_date')) or date.today(),
            referral_type=request.form['referral_type'],
            referred_to=request.form['referred_to'].strip(),
            contact_info=request.form.get('contact_info', '').strip(),
            reason=request.form.get('reason', '').strip(),
            urgency=request.form.get('urgency', 'routine'),
            status=request.form.get('status', 'pending'),
            follow_up_date=parse_date(request.form.get('follow_up_date')),
            consent_obtained='consent_obtained' in request.form,
            notes=request.form.get('notes', '').strip(),
            service_record_id=int(request.form['service_record_id']) if request.form.get('service_record_id') else None,
        )
        db.session.add(ref)
        db.session.commit()
        log_action('create', 'referral', ref.id,
                   f'Created referral to {ref.referred_to}')
        flash('Referral created.', 'success')
        return redirect(url_for('referrals.view', id=ref.id))

    student_id = request.args.get('student_id', '')
    service_record_id = request.args.get('service_record_id', '')
    referred_to = request.args.get('referred_to', '')
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active'
    ).order_by(Student.last_name).all()
    return render_template('referrals/add.html',
        students=students, preselected_student=student_id,
        service_record_id=service_record_id, referred_to_prefill=referred_to,
        referral_types=Referral.REFERRAL_TYPES,
        urgency_levels=Referral.URGENCY_LEVELS,
        statuses=Referral.STATUSES)


@referrals_bp.route('/<int:id>')
@login_required
def view(id):
    ref = owned_or_404(Referral, id)
    log_action('view', 'referral', ref.id)
    return render_template('referrals/view.html', referral=ref,
        statuses=Referral.STATUSES)


@referrals_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    ref = owned_or_404(Referral, id)
    if request.method == 'POST':
        ref.referral_date = parse_date(request.form.get('referral_date')) or ref.referral_date
        ref.referral_type = request.form['referral_type']
        ref.referred_to = request.form['referred_to'].strip()
        ref.contact_info = request.form.get('contact_info', '').strip()
        ref.reason = request.form.get('reason', '').strip()
        ref.urgency = request.form.get('urgency', 'routine')
        ref.status = request.form.get('status', ref.status)
        ref.contacted_date = parse_date(request.form.get('contacted_date'))
        ref.accepted_date = parse_date(request.form.get('accepted_date'))
        ref.completed_date = parse_date(request.form.get('completed_date'))
        ref.outcome = request.form.get('outcome', '').strip()
        ref.follow_up_date = parse_date(request.form.get('follow_up_date'))
        ref.follow_up_notes = request.form.get('follow_up_notes', '').strip()
        ref.consent_obtained = 'consent_obtained' in request.form
        ref.notes = request.form.get('notes', '').strip()
        db.session.commit()
        log_action('update', 'referral', ref.id)
        flash('Referral updated.', 'success')
        return redirect(url_for('referrals.view', id=ref.id))

    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id
    ).order_by(Student.last_name).all()
    return render_template('referrals/edit.html', referral=ref,
        students=students, referral_types=Referral.REFERRAL_TYPES,
        urgency_levels=Referral.URGENCY_LEVELS, statuses=Referral.STATUSES)


@referrals_bp.route('/<int:id>/status', methods=['POST'])
@login_required
def update_status(id):
    """AJAX-friendly status update."""
    ref = owned_or_404(Referral, id)
    new_status = request.form.get('status') or (request.get_json() or {}).get('status')
    if not new_status or new_status not in dict(Referral.STATUSES):
        return jsonify({'ok': False, 'error': 'Invalid status'}), 400

    ref.status = new_status
    today = date.today()
    if new_status == 'contacted' and not ref.contacted_date:
        ref.contacted_date = today
    if new_status == 'in_progress' and not ref.accepted_date:
        ref.accepted_date = today
    if new_status == 'completed' and not ref.completed_date:
        ref.completed_date = today

    db.session.commit()
    log_action('update', 'referral', ref.id, f'Status -> {new_status}')

    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'ok': True, 'status': ref.status, 'label': ref.status_label})
    flash(f'Referral marked {ref.status_label}.', 'success')
    return redirect(url_for('referrals.view', id=ref.id))


@referrals_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    ref = owned_or_404(Referral, id)
    log_action('delete', 'referral', ref.id)
    db.session.delete(ref)
    db.session.commit()
    flash('Referral deleted.', 'warning')
    return redirect(url_for('referrals.index'))
