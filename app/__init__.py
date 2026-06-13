from flask import Flask, jsonify, request, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect, CSRFError
from config import Config
import os

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'
# Invalidate the session if the client's remote address / user-agent fingerprint
# changes — cheap hardening against session hijacking of FERPA data.
login_manager.session_protection = 'strong'
csrf = CSRFProtect()


def _add_missing_indexes(app):
    """Create indexes on frequently-filtered foreign key columns."""
    import sqlalchemy
    indexes = [
        ('ix_notes_author_id', 'notes', 'author_id'),
        ('ix_service_records_counselor_id', 'service_records', 'counselor_id'),
        ('ix_calendar_events_owner_id', 'calendar_events', 'owner_id'),
        ('ix_meeting_notes_author_id', 'meeting_notes', 'author_id'),
        ('ix_grades_student_id', 'grades', 'student_id'),
        ('ix_attendance_student_id', 'attendance_records', 'student_id'),
    ]
    for idx_name, table, column in indexes:
        try:
            db.session.execute(sqlalchemy.text(
                f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({column})"
            ))
        except Exception:
            pass  # Table may not exist yet
    db.session.commit()


def _add_missing_columns(app):
    """Add any columns defined in models but missing from the SQLite database.

    Uses a hash of the model schema to skip introspection when nothing changed.
    """
    import hashlib, sqlalchemy

    schema_sig = hashlib.md5(
        str(sorted(
            (t, sorted(c.name for c in cols.columns))
            for t, cols in db.metadata.tables.items()
        )).encode()
    ).hexdigest()

    cache_file = os.path.join(app.instance_path, '.schema_hash')
    os.makedirs(app.instance_path, exist_ok=True)
    try:
        if os.path.isfile(cache_file) and open(cache_file).read().strip() == schema_sig:
            return
    except OSError:
        pass

    inspector = sqlalchemy.inspect(db.engine)
    changed = False
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
                    nullable = ""
                sql = f"ALTER TABLE {table_name} ADD COLUMN {col.name} {col_type}{nullable}{default}"
                db.session.execute(sqlalchemy.text(sql))
                app.logger.info(f"Added missing column: {table_name}.{col.name}")
                changed = True
    if changed:
        db.session.commit()

    with open(cache_file, 'w') as f:
        f.write(schema_sig)


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
    try:
        from app.routes.google_auth import google_auth_bp
    except ImportError as e:
        google_auth_bp = None
        app.logger.info(f"Google integration unavailable: {e}")
    from app.routes.availability import availability_bp
    from app.routes.alerts import alerts_bp
    from app.routes.analytics import analytics_bp
    from app.routes.setup import setup_bp
    try:
        from app.routes.meeting_notes import meeting_notes_bp
    except ImportError as e:
        meeting_notes_bp = None
        app.logger.info(f"Meeting notes (audio transcription) unavailable: {e}")
    from app.routes.search import search_bp
    from app.routes.mail_merge import mail_merge_bp
    from app.routes.academic_plan import academic_plan_bp
    from app.routes.college_career import college_career_bp
    from app.routes.ai_tools import ai_tools_bp
    from app.routes.knowledge_base import kb_bp
    from app.routes.admin import admin_bp
    from app.routes.student_portal import student_portal_bp
    from app.routes.referrals import referrals_bp
    from app.routes.goals import goals_bp
    from app.routes.communications import communications_bp
    from app.routes.groups import groups_bp
    from app.routes.consents import consents_bp
    from app.routes.interventions import interventions_bp
    from app.routes.screenings import screenings_bp
    from app.routes.documents import documents_bp
    from app.routes.post_grad import post_grad_bp
    from app.routes.elpac import elpac_bp
    from app.routes.staff import staff_bp

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
    if google_auth_bp:
        app.register_blueprint(google_auth_bp, url_prefix='/google')
    app.register_blueprint(availability_bp, url_prefix='/scheduling')
    app.register_blueprint(alerts_bp, url_prefix='/alerts')
    app.register_blueprint(analytics_bp, url_prefix='/analytics')
    app.register_blueprint(setup_bp)
    if meeting_notes_bp:
        app.register_blueprint(meeting_notes_bp, url_prefix='/meeting-notes')
    app.register_blueprint(search_bp)
    app.register_blueprint(mail_merge_bp, url_prefix='/mail-merge')
    app.register_blueprint(academic_plan_bp, url_prefix='/academic-plan')
    app.register_blueprint(college_career_bp, url_prefix='/college-career')
    app.register_blueprint(ai_tools_bp, url_prefix='/ai-tools')
    app.register_blueprint(kb_bp, url_prefix='/knowledge-base')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(student_portal_bp, url_prefix='/student-portal')
    app.register_blueprint(referrals_bp, url_prefix='/referrals')
    app.register_blueprint(goals_bp, url_prefix='/goals')
    app.register_blueprint(communications_bp, url_prefix='/communications')
    app.register_blueprint(groups_bp, url_prefix='/groups')
    app.register_blueprint(consents_bp, url_prefix='/consents')
    app.register_blueprint(interventions_bp, url_prefix='/interventions')
    app.register_blueprint(screenings_bp, url_prefix='/screenings')
    app.register_blueprint(documents_bp, url_prefix='/documents')
    app.register_blueprint(post_grad_bp, url_prefix='/post-grad')
    app.register_blueprint(elpac_bp, url_prefix='/elpac')
    app.register_blueprint(staff_bp, url_prefix='/staff')

    # Demo mode: register zero-friction auto-login + reset routes
    if os.environ.get('COUNSELOR_DEMO') == '1':
        from app.routes.demo import demo_bp
        app.register_blueprint(demo_bp)

    # Make the session permanent so PERMANENT_SESSION_LIFETIME (30 min) actually
    # applies as a sliding idle-timeout. Without this the cookie is a non-permanent
    # session cookie that lives until the browser closes — the advertised FERPA
    # auto-logout never fires.
    @app.before_request
    def make_session_permanent():
        from flask import session
        session.permanent = True

    # First-run setup redirect (cached after first successful check)
    @app.before_request
    def check_setup():
        if getattr(app, '_setup_done', False):
            return
        from flask import redirect, url_for
        allowed = ('/setup', '/static', '/scheduling/book/', '/student-portal/')
        if any(request.path.startswith(p) for p in allowed):
            return
        from app.routes.setup import needs_setup
        if needs_setup():
            return redirect(url_for('setup.index'))
        else:
            app._setup_done = True

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

    # Cache-bust static assets by file mtime so browsers refetch on change.
    @app.context_processor
    def inject_static_version():
        def static_v(filename):
            try:
                return int(os.path.getmtime(os.path.join(app.static_folder, filename)))
            except OSError:
                return 0
        return {'static_v': static_v}

    # Per-request data-state flags for progressive disclosure (sidebar
    # gating, dashboard sections, AI button visibility).
    @app.context_processor
    def inject_app_state():
        from flask_login import current_user
        if not current_user.is_authenticated:
            return {'app_state': {}}
        from app.utils.app_state import compute_state
        return {'app_state': compute_state(current_user)}

    # Demo-mode flag: drives the yellow banner and the visible "Reset Demo"
    # button. Set by the USB launcher; never set in real installs.
    @app.context_processor
    def inject_demo_mode():
        return {'demo_mode': os.environ.get('COUNSELOR_DEMO') == '1'}

    # Content-Security-Policy. 'unsafe-inline' is required because the app uses
    # inline <script>/<style>/onclick throughout; even so, locking default-src
    # to 'self' blocks data exfiltration to arbitrary hosts (the local-only FERPA
    # promise) and frame-ancestors/base-uri/form-action block clickjacking and
    # base-tag hijacking. 'data:' covers the theme SVG/data-URI backgrounds;
    # cdnjs is the single external dependency (pdf.js on the transcript-import page).
    CSP = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        # pdf.js (vendored locally) spins up its renderer as a blob: worker.
        "worker-src 'self' blob:; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'self'; "
        "form-action 'self'"
    )

    # Security + cache headers
    @app.after_request
    def set_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        # Don't clobber the tighter sandbox CSP that the logo routes set themselves.
        response.headers.setdefault('Content-Security-Policy', CSP)
        # HSTS only matters (and is only honored) over HTTPS; emit it when the
        # deployment opts into Secure cookies (i.e. is behind TLS).
        if app.config.get('SESSION_COOKIE_SECURE'):
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        # Cache static assets so browsers don't re-download CSS/JS every page load
        if request.path.startswith('/static/'):
            response.headers['Cache-Control'] = 'public, max-age=43200'
        # Service worker must be able to control the root scope and always load fresh
        if request.path == '/static/sw.js':
            response.headers['Service-Worker-Allowed'] = '/'
            response.headers['Cache-Control'] = 'no-cache'
        return response

    # Graceful error pages — never leak a stack trace to the browser.
    @app.errorhandler(404)
    def handle_404(e):
        if request.path.startswith(('/course-catalog/api/', '/ai/')) or request.is_json:
            return jsonify({'ok': False, 'error': 'Not found.'}), 404
        try:
            return render_template('errors/404.html'), 404
        except Exception:
            return 'Not found.', 404

    @app.errorhandler(500)
    def handle_500(e):
        db.session.rollback()
        if request.path.startswith(('/course-catalog/api/', '/ai/')) or request.is_json:
            return jsonify({'ok': False, 'error': 'Server error.'}), 500
        try:
            return render_template('errors/500.html'), 500
        except Exception:
            return 'Server error.', 500

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
        from app.models import attendance, grade, iep504, availability, meeting_note, import_log, elpac
        from app.models import academic_plan, college_career, ai_tool_history
        from app.models import knowledge_base
        from app.models import referral, goal, communication, group, consent
        from app.models import intervention, screening, document, post_grad
        from app.models import asca_program
        from app.models import rollover
        from app.models import school_calendar
        from app.utils.alert_engine import AlertCache  # noqa: F401 — register table
        db.create_all()

        # Auto-migrate: add any missing columns/indexes to existing tables
        _add_missing_columns(app)
        _add_missing_indexes(app)

        # Seed district school calendars (idempotent, non-destructive)
        try:
            from app.utils.calendar_seed import ensure_calendars_seeded
            ensure_calendars_seeded()
        except Exception:
            db.session.rollback()

        # Demo mode: seed curated dataset and skip the default-counselor setup
        from app.models.user import User
        if os.environ.get('COUNSELOR_DEMO') == '1':
            from app.utils.demo_seed import ensure_seeded
            ensure_seeded(app)
        elif not User.query.first():
            # Create default admin user if none exists
            default_user = User(
                username='counselor',
                display_name='School Counselor',
                role='counselor'
            )
            default_user.set_password('changeme')
            db.session.add(default_user)
            db.session.commit()
        else:
            # Upgrade path: mark existing users with notes/students as setup-complete
            from app.models.student import Student
            for u in User.query.filter_by(setup_completed=False).all():
                has_data = Student.query.filter_by(assigned_counselor_id=u.id).first()
                if has_data:
                    u.setup_completed = True
            db.session.commit()

    return app
