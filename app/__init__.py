from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect, CSRFError
from config import Config
import os

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'
csrf = CSRFProtect()


def _add_missing_columns(app):
    """Add any columns defined in models but missing from the SQLite database."""
    import sqlalchemy
    inspector = sqlalchemy.inspect(db.engine)
    for table_name, table in db.metadata.tables.items():
        if not inspector.has_table(table_name):
            continue
        existing = {col['name'] for col in inspector.get_columns(table_name)}
        for col in table.columns:
            if col.name not in existing:
                col_type = col.type.compile(db.engine.dialect)
                default = ''
                if col.default is not None and col.default.is_scalar:
                    val = col.default.arg
                    if isinstance(val, bool):
                        default = f" DEFAULT {1 if val else 0}"
                    elif isinstance(val, str):
                        default = f" DEFAULT '{val}'"
                    elif isinstance(val, (int, float)):
                        default = f" DEFAULT {val}"
                nullable = "" if col.nullable else " NOT NULL"
                if nullable and not default:
                    # SQLite can't add NOT NULL without default; make nullable
                    nullable = ""
                sql = f"ALTER TABLE {table_name} ADD COLUMN {col.name} {col_type}{nullable}{default}"
                db.session.execute(sqlalchemy.text(sql))
                app.logger.info(f"Added missing column: {table_name}.{col.name}")
    db.session.commit()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    os.makedirs(app.config.get('UPLOAD_FOLDER', 'data/uploads'), exist_ok=True)
    os.makedirs(app.config.get('BACKUP_DIR', 'data/backups'), exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.caseload import caseload_bp
    from app.routes.calendar import calendar_bp
    from app.routes.notes import notes_bp
    from app.routes.activity_log import activity_log_bp
    from app.routes.service_log import service_log_bp
    from app.routes.reports import reports_bp
    from app.routes.course_catalog import course_catalog_bp
    from app.routes.glossary import glossary_bp
    from app.routes.settings import settings_bp
    from app.routes.ai import ai_bp
    from app.routes.data_import import data_import_bp
    from app.routes.followups import followups_bp
    from app.routes.graduation import graduation_bp
    from app.routes.iep504 import iep504_bp
    from app.routes.meeting_prep import meeting_prep_bp
    from app.routes.email_drafts import email_drafts_bp
    from app.routes.google_auth import google_auth_bp
    from app.routes.availability import availability_bp
    from app.routes.alerts import alerts_bp
    from app.routes.analytics import analytics_bp
    from app.routes.setup import setup_bp
    from app.routes.meeting_notes import meeting_notes_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(caseload_bp, url_prefix='/caseload')
    app.register_blueprint(calendar_bp, url_prefix='/calendar')
    app.register_blueprint(notes_bp, url_prefix='/notes')
    app.register_blueprint(activity_log_bp, url_prefix='/activity-log')
    app.register_blueprint(service_log_bp, url_prefix='/service-log')
    app.register_blueprint(reports_bp, url_prefix='/reports')
    app.register_blueprint(course_catalog_bp, url_prefix='/course-catalog')
    app.register_blueprint(glossary_bp, url_prefix='/glossary')
    app.register_blueprint(settings_bp, url_prefix='/settings')
    app.register_blueprint(ai_bp, url_prefix='/ai')
    app.register_blueprint(data_import_bp, url_prefix='/data-import')
    app.register_blueprint(followups_bp, url_prefix='/follow-ups')
    app.register_blueprint(graduation_bp, url_prefix='/graduation')
    app.register_blueprint(iep504_bp, url_prefix='/iep504')
    app.register_blueprint(meeting_prep_bp, url_prefix='/meeting-prep')
    app.register_blueprint(email_drafts_bp, url_prefix='/email-drafts')
    app.register_blueprint(google_auth_bp, url_prefix='/google')
    app.register_blueprint(availability_bp, url_prefix='/scheduling')
    app.register_blueprint(alerts_bp, url_prefix='/alerts')
    app.register_blueprint(analytics_bp, url_prefix='/analytics')
    app.register_blueprint(setup_bp)
    app.register_blueprint(meeting_notes_bp, url_prefix='/meeting-notes')

    # First-run setup redirect
    @app.before_request
    def check_setup():
        from flask import redirect, url_for
        # Allow setup routes, static files, and public booking pages
        allowed = ('/setup', '/static', '/scheduling/book/')
        if any(request.path.startswith(p) for p in allowed):
            return
        from app.routes.setup import needs_setup
        if needs_setup():
            return redirect(url_for('setup.index'))

    # Theme context processor — injects user_theme into all templates
    @app.context_processor
    def inject_theme():
        from flask_login import current_user
        if current_user.is_authenticated:
            return {
                'user_theme': current_user.theme_preference or 'light',
                'user_reduced_motion': current_user.reduced_motion or False
            }
        return {'user_theme': 'light', 'user_reduced_motion': False}

    # Security headers
    @app.after_request
    def set_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return response

    # Return JSON (not HTML) for CSRF errors on API endpoints
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        if request.path.startswith('/course-catalog/api/') or request.is_json:
            return jsonify({'ok': False, 'error': 'CSRF token missing or expired. Please refresh the page and try again.'}), 400
        from flask import abort
        abort(400)

    # Return JSON for login-required failures on API endpoints
    @login_manager.unauthorized_handler
    def unauthorized_api():
        if request.path.startswith('/course-catalog/api/') or request.is_json:
            return jsonify({'ok': False, 'error': 'Session expired. Please refresh the page and log in again.'}), 401
        from flask import redirect, url_for
        return redirect(url_for('auth.login'))

    with app.app_context():
        from app.models import user, student, note, activity, calendar_event
        from app.models import service_record, course, glossary_term, transcript
        from app.models import attendance, grade, iep504, availability, meeting_note, import_log
        from app.utils.alert_engine import AlertCache  # noqa: F401 — register table
        db.create_all()

        # Auto-migrate: add any missing columns to existing tables
        _add_missing_columns(app)

        # Create default admin user if none exists
        from app.models.user import User
        if not User.query.first():
            default_user = User(
                username='counselor',
                display_name='School Counselor',
                role='counselor'
            )
            default_user.set_password('changeme')
            db.session.add(default_user)
            db.session.commit()
        else:
            # Upgrade path: mark existing users who have real data as setup-complete
            for u in User.query.filter_by(setup_completed=False).all():
                if not u.check_password('changeme'):
                    u.setup_completed = True
            db.session.commit()

    return app
