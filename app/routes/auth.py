import time
from urllib.parse import urlparse
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from app.models.user import User
from app.utils.audit import log_action
from datetime import datetime, timezone


def _is_safe_redirect(target):
    """Reject external / open-redirect URLs."""
    if not target:
        return False
    parsed = urlparse(target)
    # Only allow relative paths (no scheme, no external host)
    return parsed.scheme == '' and parsed.netloc == ''


# ── Brute-force throttle (in-process; this app runs single-process locally) ──
_MAX_ATTEMPTS = 5          # failures allowed within the window before lockout
_WINDOW_SECONDS = 300      # 5-minute rolling window
_failed_attempts = {}      # (ip, username) -> [timestamps]

# Constant dummy hash: verified when the username doesn't exist so the response
# time of "no such user" matches "wrong password", defeating user enumeration.
_DUMMY_HASH = generate_password_hash('counselor-assistant-timing-equalizer')


def _recent_failures(key):
    now = time.time()
    attempts = [t for t in _failed_attempts.get(key, []) if now - t < _WINDOW_SECONDS]
    if attempts:
        _failed_attempts[key] = attempts
    else:
        _failed_attempts.pop(key, None)
    return attempts


auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # Redirect to setup wizard if first run
    from app.routes.setup import needs_setup
    if needs_setup():
        return redirect(url_for('setup.index'))

    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        key = (request.remote_addr or 'unknown', username.lower())

        # Lockout: too many recent failures from this IP+username.
        if len(_recent_failures(key)) >= _MAX_ATTEMPTS:
            log_action('login_blocked', 'user', None,
                       f'Rate-limited login for "{username}" from {request.remote_addr}')
            flash('Too many failed attempts. Please wait a few minutes and try again.', 'danger')
            return render_template('auth/login.html'), 429

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            _failed_attempts.pop(key, None)
            login_user(user, remember=False)
            user.last_login = datetime.now(timezone.utc)
            db.session.commit()
            log_action('login', 'user', user.id)
            next_page = request.args.get('next')
            if not _is_safe_redirect(next_page):
                next_page = None
            return redirect(next_page or url_for('dashboard.index'))
        else:
            # Equalize timing for non-existent usernames (anti-enumeration).
            if not user:
                check_password_hash(_DUMMY_HASH, password)
            _failed_attempts.setdefault(key, []).append(time.time())
            log_action('login_failed', 'user', user.id if user else None,
                       f'Failed login for "{username}" from {request.remote_addr}')
            flash('Invalid username or password.', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    log_action('logout', 'user', current_user.id)
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_pw = request.form.get('current_password', '')
        new_pw = request.form.get('new_password', '')
        confirm_pw = request.form.get('confirm_password', '')

        if not current_user.check_password(current_pw):
            flash('Current password is incorrect.', 'danger')
        elif new_pw != confirm_pw:
            flash('New passwords do not match.', 'danger')
        elif len(new_pw) < 8:
            flash('Password must be at least 8 characters.', 'danger')
        else:
            current_user.set_password(new_pw)
            db.session.commit()
            log_action('change_password', 'user', current_user.id)
            flash('Password changed successfully.', 'success')
            return redirect(url_for('dashboard.index'))

    return render_template('auth/change_password.html')
