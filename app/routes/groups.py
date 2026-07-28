from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models.group import (CounselingGroup, GroupMember, GroupSession, GroupAttendance)
from app.models.student import Student
from app.utils.audit import log_action
from app.utils.helpers import parse_date
from app.utils.roles import owned_or_404, caseload_student_or_404

groups_bp = Blueprint('groups', __name__)


def _owned_group_child_or_404(model, obj_id):
    """Fetch a GroupMember/GroupSession scoped to a group the caller owns.

    Neither child model has an owner column — only group_id — so ownership has
    to be resolved through the parent group. Delegates the actual check to
    owned_or_404 so the admin bypass and 404-not-403 behaviour stay consistent.
    """
    obj = model.query.get_or_404(obj_id)
    owned_or_404(CounselingGroup, obj.group_id)
    return obj


@groups_bp.route('/')
@login_required
def index():
    status = request.args.get('status', '')
    query = CounselingGroup.query.filter_by(counselor_id=current_user.id)
    if status:
        query = query.filter_by(status=status)
    groups = query.order_by(CounselingGroup.start_date.desc().nullslast(),
                            CounselingGroup.created_at.desc()).all()

    return render_template('groups/index.html', groups=groups, status=status,
        statuses=CounselingGroup.STATUSES)


@groups_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if request.method == 'POST':
        group = CounselingGroup(
            counselor_id=current_user.id,
            name=request.form['name'].strip(),
            group_type=request.form.get('group_type', ''),
            asca_domain=request.form.get('asca_domain', ''),
            description=request.form.get('description', '').strip(),
            schedule=request.form.get('schedule', '').strip(),
            location=request.form.get('location', '').strip(),
            start_date=parse_date(request.form.get('start_date')),
            end_date=parse_date(request.form.get('end_date')),
            status=request.form.get('status', 'planning'),
            pre_assessment=request.form.get('pre_assessment', '').strip(),
            post_assessment=request.form.get('post_assessment', '').strip(),
        )
        db.session.add(group)
        db.session.commit()
        log_action('create', 'counseling_group', group.id, f'Created group: {group.name}')
        flash('Group created.', 'success')
        return redirect(url_for('groups.view', id=group.id))

    return render_template('groups/add.html',
        group_types=CounselingGroup.GROUP_TYPES,
        statuses=CounselingGroup.STATUSES,
        asca_domains=[('academic', 'Academic'), ('career', 'Career'),
                      ('social_emotional', 'Social/Emotional')])


@groups_bp.route('/<int:id>')
@login_required
def view(id):
    group = owned_or_404(CounselingGroup, id)
    log_action('view', 'counseling_group', group.id)
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active'
    ).order_by(Student.last_name).all()
    enrolled_ids = {m.student_id for m in group.members}
    available = [s for s in students if s.id not in enrolled_ids]
    return render_template('groups/view.html', group=group,
        available_students=available)


@groups_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    group = owned_or_404(CounselingGroup, id)
    if request.method == 'POST':
        group.name = request.form['name'].strip()
        group.group_type = request.form.get('group_type', '')
        group.asca_domain = request.form.get('asca_domain', '')
        group.description = request.form.get('description', '').strip()
        group.schedule = request.form.get('schedule', '').strip()
        group.location = request.form.get('location', '').strip()
        group.start_date = parse_date(request.form.get('start_date'))
        group.end_date = parse_date(request.form.get('end_date'))
        group.status = request.form.get('status', group.status)
        group.pre_assessment = request.form.get('pre_assessment', '').strip()
        group.post_assessment = request.form.get('post_assessment', '').strip()
        group.outcome_summary = request.form.get('outcome_summary', '').strip()
        db.session.commit()
        log_action('update', 'counseling_group', group.id)
        flash('Group updated.', 'success')
        return redirect(url_for('groups.view', id=group.id))

    return render_template('groups/edit.html', group=group,
        group_types=CounselingGroup.GROUP_TYPES,
        statuses=CounselingGroup.STATUSES)


@groups_bp.route('/<int:id>/add-member', methods=['POST'])
@login_required
def add_member(id):
    group = owned_or_404(CounselingGroup, id, owner_attr='counselor_id')
    student_id = caseload_student_or_404(request.form.get('student_id')).id
    if not GroupMember.query.filter_by(group_id=group.id, student_id=student_id).first():
        member = GroupMember(group_id=group.id, student_id=student_id,
                             consent_status=request.form.get('consent_status', 'pending'))
        db.session.add(member)
        db.session.commit()
        log_action('create', 'group_member', member.id)
        flash('Student added to group.', 'success')
    return redirect(url_for('groups.view', id=group.id))


@groups_bp.route('/member/<int:member_id>/remove', methods=['POST'])
@login_required
def remove_member(member_id):
    member = _owned_group_child_or_404(GroupMember, member_id)
    group_id = member.group_id
    log_action('delete', 'group_member', member.id)
    db.session.delete(member)
    db.session.commit()
    flash('Member removed.', 'warning')
    return redirect(url_for('groups.view', id=group_id))


@groups_bp.route('/member/<int:member_id>/update', methods=['POST'])
@login_required
def update_member(member_id):
    member = _owned_group_child_or_404(GroupMember, member_id)
    member.consent_status = request.form.get('consent_status', member.consent_status)
    member.consent_date = parse_date(request.form.get('consent_date'))
    member.pre_score = request.form.get('pre_score', '').strip()
    member.post_score = request.form.get('post_score', '').strip()
    member.notes = request.form.get('notes', '').strip()
    db.session.commit()
    log_action('update', 'group_member', member.id)
    flash('Member updated.', 'success')
    return redirect(url_for('groups.view', id=member.group_id))


@groups_bp.route('/<int:id>/session/add', methods=['POST'])
@login_required
def add_session(id):
    group = owned_or_404(CounselingGroup, id)
    session = GroupSession(
        group_id=group.id,
        session_date=parse_date(request.form.get('session_date')) or date.today(),
        session_number=int(request.form['session_number']) if request.form.get('session_number') else None,
        topic=request.form.get('topic', '').strip(),
        notes=request.form.get('notes', '').strip(),
        duration_minutes=int(request.form['duration_minutes']) if request.form.get('duration_minutes') else None,
    )
    db.session.add(session)
    db.session.flush()

    # Initialize attendance for all current members
    for member in group.members:
        att_status = request.form.get(f'attend_{member.student_id}', 'present')
        att = GroupAttendance(session_id=session.id, student_id=member.student_id,
                              status=att_status)
        db.session.add(att)

    db.session.commit()
    log_action('create', 'group_session', session.id)
    flash('Session logged.', 'success')
    return redirect(url_for('groups.view', id=group.id))


@groups_bp.route('/session/<int:sid>/delete', methods=['POST'])
@login_required
def delete_session(sid):
    session = _owned_group_child_or_404(GroupSession, sid)
    group_id = session.group_id
    log_action('delete', 'group_session', session.id)
    db.session.delete(session)
    db.session.commit()
    return redirect(url_for('groups.view', id=group_id))


@groups_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    group = owned_or_404(CounselingGroup, id)
    log_action('delete', 'counseling_group', group.id)
    db.session.delete(group)
    db.session.commit()
    flash('Group deleted.', 'warning')
    return redirect(url_for('groups.index'))
