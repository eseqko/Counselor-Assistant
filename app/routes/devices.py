from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, make_response, current_app
)
from flask_login import login_required, current_user
from app import db
from app.models.device import DeviceInvite, DeviceToken
from app.utils.audit import log_action

devices_bp = Blueprint('devices', __name__)


def _require_direct_login():
    """Block device-authenticated sessions from managing devices."""
    if getattr(request, 'device_token', None):
        flash('Device management requires a direct login.', 'warning')
        return redirect(url_for('dashboard.index'))
    return None


@devices_bp.route('/')
@login_required
def index():
    blocked = _require_direct_login()
    if blocked:
        return blocked

    invites = DeviceInvite.query.filter_by(
        created_by_id=current_user.id, used=False
    ).order_by(DeviceInvite.created_at.desc()).all()
    # Filter out expired invites from display
    invites = [i for i in invites if i.is_valid]

    devices = DeviceToken.query.filter_by(
        user_id=current_user.id
    ).order_by(DeviceToken.created_at.desc()).all()

    return render_template('devices/index.html', invites=invites, devices=devices)


@devices_bp.route('/invite', methods=['POST'])
@login_required
def create_invite():
    blocked = _require_direct_login()
    if blocked:
        return blocked

    invite = DeviceInvite.generate(current_user.id)
    log_action('device_invite_created', 'device_invite', invite.id,
               f'Invite code created (expires {invite.expires_at.strftime("%m/%d/%Y %I:%M %p")} UTC)')
    flash('Invite link created! Share it with your other device. It expires in 24 hours.', 'success')
    return redirect(url_for('devices.index'))


@devices_bp.route('/invite/<int:invite_id>/revoke', methods=['POST'])
@login_required
def revoke_invite(invite_id):
    blocked = _require_direct_login()
    if blocked:
        return blocked

    invite = DeviceInvite.query.get_or_404(invite_id)
    if invite.created_by_id != current_user.id:
        flash('Not authorized.', 'danger')
        return redirect(url_for('devices.index'))

    invite.used = True  # Mark as used so it can't be redeemed
    db.session.commit()
    log_action('invite_revoked', 'device_invite', invite.id)
    flash('Invite cancelled.', 'info')
    return redirect(url_for('devices.index'))


@devices_bp.route('/register/<code>', methods=['GET', 'POST'])
def register(code):
    invite = DeviceInvite.query.filter_by(code=code).first()
    if not invite or not invite.is_valid:
        return render_template('devices/register.html', error='This invite link is invalid or has expired.')

    if request.method == 'POST':
        device_name = request.form.get('device_name', '').strip()
        if not device_name or len(device_name) > 120:
            flash('Please enter a device name (max 120 characters).', 'danger')
            return render_template('devices/register.html', invite=invite)

        # Create the device token
        device, plain_token = DeviceToken.create(
            user_id=invite.created_by_id,
            device_name=device_name,
            secret_key=current_app.config['SECRET_KEY'],
            invite_id=invite.id,
        )

        # Mark invite as used
        invite.used = True
        invite.used_at = __import__('datetime').datetime.now(__import__('datetime').timezone.utc)
        db.session.commit()

        log_action('device_registered', 'device_token', device.id,
                   f'Device "{device_name}" registered')

        # Set the device_token cookie and redirect to dashboard
        response = make_response(redirect(url_for('dashboard.index')))
        response.set_cookie(
            'device_token',
            plain_token,
            max_age=365 * 24 * 3600,  # 1 year
            httponly=True,
            samesite='Lax',
        )
        return response

    return render_template('devices/register.html', invite=invite)


@devices_bp.route('/<int:device_id>/revoke', methods=['POST'])
@login_required
def revoke_device(device_id):
    blocked = _require_direct_login()
    if blocked:
        return blocked

    device = DeviceToken.query.get_or_404(device_id)
    if device.user_id != current_user.id:
        flash('Not authorized.', 'danger')
        return redirect(url_for('devices.index'))

    device.is_revoked = True
    db.session.commit()
    log_action('device_revoked', 'device_token', device.id,
               f'Device "{device.device_name}" access revoked')
    flash(f'Access revoked for "{device.device_name}".', 'success')
    return redirect(url_for('devices.index'))
