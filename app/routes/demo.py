"""Demo-mode-only routes: zero-friction auto-login and demo-data reset.

Registered ONLY when COUNSELOR_DEMO=1 (see app/__init__.py). Never available
in real installs.
"""
from datetime import datetime, timezone

from flask import Blueprint, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user

from app import db
from app.models.user import User


demo_bp = Blueprint('demo', __name__)


@demo_bp.route('/demo-login')
def login():
    """Log in as the demo user with no prompt and redirect to the dashboard."""
    user = User.query.filter_by(username='demo').first()
    if not user:
        # Seeder hasn't run yet (or failed). Run it now.
        from app.utils.demo_seed import ensure_seeded
        ensure_seeded(current_app._get_current_object())
        user = User.query.filter_by(username='demo').first()
        if not user:
            flash('Demo data could not be loaded. Check the application logs.', 'danger')
            return redirect(url_for('auth.login'))

    logout_user()
    login_user(user, remember=False)
    user.last_login = datetime.now(timezone.utc)
    db.session.commit()
    return redirect(url_for('dashboard.index'))


@demo_bp.route('/demo-reset', methods=['POST'])
def reset():
    """Wipe demo data and re-seed from data/demo-seed.json."""
    from app.utils.demo_seed import reset_and_reseed
    logout_user()
    reset_and_reseed(current_app._get_current_object())
    flash('Demo data reset. Welcome back!', 'success')
    return redirect(url_for('demo.login'))
