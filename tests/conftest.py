"""Shared pytest fixtures.

Environment variables MUST be set before `app` is imported, so they live at
module top. We run in demo mode against a throwaway SQLite file in a temp dir,
which gives us a realistic seeded caseload to test against.
"""
import os
import tempfile
import uuid

import pytest

os.environ.setdefault('COUNSELOR_DEMO', '1')
os.environ.setdefault('COUNSELOR_DATA_DIR', tempfile.mkdtemp(prefix='counselor-test-'))

from app import create_app, db as _db  # noqa: E402


@pytest.fixture(scope='session')
def app():
    application = create_app()
    # TESTING stays False on purpose: we want unhandled exceptions to render as
    # 500 responses (not re-raise) so the route sweep can assert on status codes.
    application.config.update(WTF_CSRF_ENABLED=False)
    yield application


@pytest.fixture
def app_ctx(app):
    """Push an application context for tests that touch the DB directly."""
    with app.app_context():
        yield


@pytest.fixture
def client(app):
    """Anonymous test client."""
    return app.test_client()


@pytest.fixture
def auth_client(app):
    """Test client already logged in as the seeded demo counselor."""
    c = app.test_client()
    c.get('/demo-login')
    return c


@pytest.fixture
def demo_user_id(app):
    from app.models.user import User
    with app.app_context():
        return User.query.filter_by(username='demo').first().id


@pytest.fixture
def as_demo_user(app):
    """Context manager: a request context with the demo counselor logged in.

    Needed for helpers like _build_student_insights_prompt that read
    flask_login.current_user.
    """
    from contextlib import contextmanager
    from flask_login import login_user
    from app.models.user import User

    @contextmanager
    def _ctx():
        with app.test_request_context():
            login_user(User.query.filter_by(username='demo').first())
            yield
    return _ctx


@pytest.fixture
def make_student(app):
    """Factory that creates a throwaway student (+optional transcript).

    Returns the new student's id. All students created during a test are
    deleted in teardown so tests stay isolated despite a shared DB file.
    Protected statuses default to False / EL=EO so rollover defaults are
    predictable; override via kwargs.
    """
    from app.models.student import Student
    from app.models.transcript import TranscriptRecord
    from app.models.user import User

    created = []

    def _make(grade=10, completed=None, wip=None, quarter=None, ag_met=1,
              credits_json=None, **attrs):
        with app.app_context():
            uid = User.query.filter_by(username='demo').first().id
            s = Student(
                student_id_number=f'T{uuid.uuid4().hex[:10]}',
                first_name='Test', last_name='Student',
                grade_level=grade, status='active',
                assigned_counselor_id=uid,
            )
            for f in ('iep_status', 'section_504', 'is_foster_youth', 'is_homeless',
                      'is_migrant_newcomer', 'is_formerly_incarcerated',
                      'is_military_connected'):
                setattr(s, f, False)
            s.el_status = 'EO'
            s.exit_date = None
            for k, v in attrs.items():
                setattr(s, k, v)
            _db.session.add(s)
            _db.session.flush()
            if completed is not None or wip is not None or quarter is not None:
                _db.session.add(TranscriptRecord(
                    student_id=s.id, quarter=quarter,
                    total_completed=float(completed or 0),
                    total_wip=float(wip or 0),
                    ag_areas_met=ag_met, ag_areas_deficient=max(0, 7 - ag_met),
                    credits_json=credits_json, risk_level='unknown',
                ))
            _db.session.commit()
            created.append(s.id)
            return s.id

    yield _make

    with app.app_context():
        for sid in created:
            TranscriptRecord.query.filter_by(student_id=sid).delete()
            s = _db.session.get(Student, sid)
            if s:
                _db.session.delete(s)
        _db.session.commit()
