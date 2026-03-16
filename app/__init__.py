from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from config import Config
import os

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'
csrf = CSRFProtect()


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

    with app.app_context():
        from app.models import user, student, note, activity, calendar_event
        from app.models import service_record, course, glossary_term
        db.create_all()

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

    return app
