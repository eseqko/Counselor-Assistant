"""Google OAuth 2.0 client — handles authorization flow and credential management.

Usage:
    1. Place your Google Cloud credentials.json in data/google_credentials.json
    2. The OAuth flow is triggered from /google/authorize
    3. Tokens are stored per-user in the database (User.google_token_json)

This module is the foundation for all Google API integrations (Calendar,
Gmail, Classroom, etc.). Scopes can be expanded in config.py.
"""
import json
import os
from flask import current_app

# google-auth packages are optional (excluded from the demo bundle). Imports
# happen inside the functions that need them so callers without these
# packages installed can still import this module.


def credentials_configured():
    """Check if Google OAuth credentials.json exists."""
    creds_file = current_app.config.get('GOOGLE_CREDENTIALS_FILE', '')
    return os.path.exists(creds_file)


def create_flow(redirect_uri):
    """Create an OAuth 2.0 flow for the authorization redirect."""
    from google_auth_oauthlib.flow import Flow
    creds_file = current_app.config['GOOGLE_CREDENTIALS_FILE']
    scopes = current_app.config['GOOGLE_SCOPES']

    flow = Flow.from_client_secrets_file(
        creds_file,
        scopes=scopes,
        redirect_uri=redirect_uri,
    )
    return flow


def get_credentials(user):
    """Load and refresh Google credentials from a User's stored token.

    Returns a valid Credentials object or None if not connected.
    """
    if not user.google_token_json:
        return None

    try:
        token_data = json.loads(user.google_token_json)
    except (json.JSONDecodeError, TypeError):
        return None

    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    creds = Credentials(
        token=token_data.get('token'),
        refresh_token=token_data.get('refresh_token'),
        token_uri=token_data.get('token_uri', 'https://oauth2.googleapis.com/token'),
        client_id=token_data.get('client_id'),
        client_secret=token_data.get('client_secret'),
        scopes=token_data.get('scopes'),
    )

    # Refresh if expired
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            save_credentials(user, creds)
        except Exception:
            # Token is invalid — user needs to re-authorize
            return None

    if not creds.valid:
        return None

    return creds


def save_credentials(user, creds):
    """Persist Google credentials to the User record."""
    from app import db
    token_data = {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': list(creds.scopes) if creds.scopes else [],
    }
    user.google_token_json = json.dumps(token_data)
    db.session.commit()


def clear_credentials(user):
    """Remove stored Google credentials."""
    from app import db
    user.google_token_json = None
    db.session.commit()


def is_connected(user):
    """Check if a user has valid Google credentials."""
    creds = get_credentials(user)
    return creds is not None and creds.valid
