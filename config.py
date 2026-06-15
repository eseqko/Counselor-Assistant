import os
import secrets

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.environ.get('COUNSELOR_DATA_DIR') or os.path.join(BASE_DIR, 'data')
os.makedirs(DATA_DIR, exist_ok=True)

# Secret key: prefer environment variable, fall back to persistent file
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    SECRET_KEY_FILE = os.path.join(DATA_DIR, '.secret_key')
    if os.path.exists(SECRET_KEY_FILE):
        with open(SECRET_KEY_FILE, 'r') as f:
            SECRET_KEY = f.read().strip()
    else:
        SECRET_KEY = secrets.token_hex(32)
        with open(SECRET_KEY_FILE, 'w') as f:
            f.write(SECRET_KEY)
        os.chmod(SECRET_KEY_FILE, 0o600)


class Config:
    SECRET_KEY = SECRET_KEY
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{os.path.join(DATA_DIR, "counselor.db")}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True

    # FERPA Compliance settings
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Strict'
    PERMANENT_SESSION_LIFETIME = 1800  # 30 minutes idle auto-logout (sliding)
    # Re-issue the cookie on every request so the 30-min window is an IDLE
    # timeout, not a fixed one — combined with session.permanent set per-request.
    SESSION_REFRESH_EACH_REQUEST = True
    # Mark the cookie Secure when served over HTTPS. Defaults off because the
    # app ships as plaintext-HTTP local/Tailscale; a Secure cookie would never
    # be sent over http:// and would silently break login. Set
    # SESSION_COOKIE_SECURE=true in the environment behind a TLS proxy.
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', '').lower() == 'true'

    # "Remember me" is disabled app-wide (all login_user(remember=False)), but
    # harden the remember cookie too in case it is ever enabled.
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = 'Strict'
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE

    # Local-only: no cloud, no external connections
    UPLOAD_FOLDER = os.path.join(DATA_DIR, 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload
    BACKUP_DIR = os.path.join(DATA_DIR, 'backups')

    # Google OAuth 2.0 — place credentials.json in data/ directory
    GOOGLE_CREDENTIALS_FILE = os.path.join(DATA_DIR, 'google_credentials.json')
    GOOGLE_SCOPES = [
        'https://www.googleapis.com/auth/calendar',
        'https://www.googleapis.com/auth/forms.body',
        'https://www.googleapis.com/auth/forms.responses.readonly',
        'https://www.googleapis.com/auth/classroom.courses.readonly',
        'https://www.googleapis.com/auth/classroom.coursework.students',
    ]
