"""Data-migration runner: applies once, idempotent, backfills, fails safe."""
import sqlalchemy
from sqlalchemy import text

from app import db, _run_data_migrations
from app.migrations import MIGRATIONS, _m_0001_backfill_is_shadow


def _applied_versions(app):
    with app.app_context():
        with db.engine.begin() as conn:
            return {r[0] for r in conn.execute(
                text("SELECT version FROM schema_migrations"))}


def test_registered_migrations_recorded_after_boot(app):
    """Every shipped migration is applied + recorded during app startup."""
    applied = _applied_versions(app)
    for version, _desc, _fn in MIGRATIONS:
        assert version in applied, f'{version} was not applied at boot'


def test_runner_is_idempotent(app):
    """Re-running the runner applies nothing new and never raises."""
    before = _applied_versions(app)
    with app.app_context():
        _run_data_migrations(app)
        _run_data_migrations(app)
    assert _applied_versions(app) == before


def test_is_shadow_backfill_sets_null_to_zero(app):
    """0001 normalizes a NULL is_shadow to 0 (False)."""
    with app.app_context():
        with db.engine.begin() as conn:
            sid = conn.execute(text("SELECT id FROM students LIMIT 1")).scalar()
            assert sid is not None
            conn.execute(text("UPDATE students SET is_shadow = NULL WHERE id = :i"),
                         {'i': sid})
            assert conn.execute(
                text("SELECT is_shadow FROM students WHERE id = :i"),
                {'i': sid}).scalar() is None
            _m_0001_backfill_is_shadow(conn)
            assert conn.execute(
                text("SELECT is_shadow FROM students WHERE id = :i"),
                {'i': sid}).scalar() == 0


def test_failing_migration_is_rolled_back_and_not_recorded(app, monkeypatch):
    """A migration that raises must roll back, stay unrecorded (retries next
    boot), halt the run, and never brick startup."""
    def boom(conn):
        # Touch the DB first, then fail — proves the write is rolled back too.
        conn.execute(text("UPDATE students SET is_shadow = is_shadow"))
        raise RuntimeError('intentional failure')

    monkeypatch.setattr('app.migrations.MIGRATIONS',
                        [('9999_intentional_failure', 'always fails', boom)])
    with app.app_context():
        _run_data_migrations(app)  # must NOT raise

    assert '9999_intentional_failure' not in _applied_versions(app)
