import os
import shutil
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
from app import db
from app.models.user import User, AuditLog
from app.utils.audit import log_action
from config import Config

settings_bp = Blueprint('settings', __name__)


@settings_bp.route('/')
@login_required
def index():
    return render_template('settings/index.html')


@settings_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_user.display_name = request.form.get('display_name', current_user.display_name)
        current_user.school_name = request.form.get('school_name', '')
        db.session.commit()
        flash('Profile updated.', 'success')
        return redirect(url_for('settings.profile'))

    return render_template('settings/profile.html')


@settings_bp.route('/audit-log')
@login_required
def audit_log():
    page = request.args.get('page', 1, type=int)
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).paginate(
        page=page, per_page=50, error_out=False)
    return render_template('settings/audit_log.html', logs=logs)


@settings_bp.route('/backup', methods=['POST'])
@login_required
def backup():
    """Create a local backup of the database."""
    backup_dir = Config.BACKUP_DIR
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(backup_dir, f'counselor_backup_{timestamp}.db')
    db_path = os.path.join(Config.DATA_DIR if hasattr(Config, 'DATA_DIR') else 'data', 'counselor.db')

    try:
        shutil.copy2(db_path, backup_path)
        log_action('backup', 'database', details=f'Backup created: {backup_path}')
        flash(f'Backup created successfully at {backup_path}', 'success')
    except Exception as e:
        flash(f'Backup failed: {str(e)}', 'danger')

    return redirect(url_for('settings.index'))


@settings_bp.route('/export-backup')
@login_required
def export_backup():
    """Download the latest backup."""
    backup_dir = Config.BACKUP_DIR
    if not os.path.exists(backup_dir):
        flash('No backups found.', 'warning')
        return redirect(url_for('settings.index'))

    backups = sorted(
        [f for f in os.listdir(backup_dir) if f.endswith('.db')],
        reverse=True
    )
    if not backups:
        flash('No backups found.', 'warning')
        return redirect(url_for('settings.index'))

    backup_path = os.path.join(backup_dir, backups[0])
    log_action('export', 'database', details='Downloaded backup')
    return send_file(backup_path, as_attachment=True)
