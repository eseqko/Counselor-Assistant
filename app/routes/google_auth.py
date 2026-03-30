"""Google OAuth 2.0 authorization routes."""
import os
from flask import Blueprint, redirect, url_for, flash, session, request
from flask_login import login_required, current_user
from app.utils.google_client import (
    credentials_configured, create_flow, save_credentials, clear_credentials,
)

google_auth_bp = Blueprint('google_auth', __name__)


@google_auth_bp.route('/authorize')
@login_required
def authorize():
    """Start the Google OAuth 2.0 flow."""
    if not credentials_configured():
        flash('Google API credentials not configured. Place credentials.json '
              'in the data/ directory.', 'danger')
        return redirect(url_for('calendar.index'))

    # Allow HTTP for local development (localhost only)
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

    redirect_uri = url_for('google_auth.callback', _external=True)
    flow = create_flow(redirect_uri)

    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent',
    )

    session['google_oauth_state'] = state
    return redirect(authorization_url)


@google_auth_bp.route('/callback')
@login_required
def callback():
    """Handle the OAuth 2.0 callback from Google."""
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

    redirect_uri = url_for('google_auth.callback', _external=True)
    flow = create_flow(redirect_uri)

    try:
        flow.fetch_token(authorization_response=request.url)
    except Exception:
        flash('Failed to complete Google authorization. Please try again.', 'danger')
        return redirect(url_for('calendar.index'))

    creds = flow.credentials
    save_credentials(current_user, creds)

    flash('Google Calendar connected successfully!', 'success')
    return redirect(url_for('calendar.index'))


@google_auth_bp.route('/disconnect', methods=['POST'])
@login_required
def disconnect():
    """Disconnect Google account by clearing stored credentials."""
    clear_credentials(current_user)
    flash('Google account disconnected.', 'info')
    return redirect(url_for('calendar.index'))
