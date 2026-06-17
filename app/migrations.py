"""Versioned, one-time data migrations.

`_add_missing_columns` in app/__init__ handles **schema** drift — it adds new
columns/indexes defined on the models to an existing SQLite database. That's
enough when all a change needs is a new (defaulted) column.

This module handles **data** drift: one-time backfills/transforms that must run
exactly once per database, in order, *after* the schema is up to date. Each
migration is recorded in a `schema_migrations` table (created on demand), so it
never re-runs — the table lives inside the database, which makes the record
intrinsically per-database (the same property that keeps the schema-hash
sentinel honest).

Adding a migration
------------------
Append a `(version, description, fn)` tuple to MIGRATIONS. `version` must be
unique and sort in apply-order (zero-padded numeric prefix). `fn(conn)` receives
a SQLAlchemy Connection already inside a transaction; raise to abort/rollback.

Write every migration to be **idempotent** (e.g. `WHERE col IS NULL`): the
version table is the primary guard, but idempotency is the safety net if a run
is interrupted before the version is recorded.
"""
from sqlalchemy import text


def _m_0001_backfill_is_shadow(conn):
    """Older `students` rows can have is_shadow = NULL (column added before a
    default existed). Caseload filters compare `is_shadow == False`, which does
    NOT match NULL in SQL — so a NULL row would slip through caseload/admin
    filters. Normalize NULL → 0 (False)."""
    conn.execute(text("UPDATE students SET is_shadow = 0 WHERE is_shadow IS NULL"))


def _m_0002_backfill_follow_up_completed(conn):
    """Normalize NULL follow_up_completed → 0 on notes and communication logs so
    the Follow-Ups digest and reminder counts treat 'never touched' as open
    consistently (the queries already OR in IS NULL, but clean data is simpler
    and avoids surprises in future aggregates)."""
    conn.execute(text(
        "UPDATE notes SET follow_up_completed = 0 WHERE follow_up_completed IS NULL"))
    conn.execute(text(
        "UPDATE communication_logs SET follow_up_completed = 0 "
        "WHERE follow_up_completed IS NULL"))


# Ordered registry. Never renumber or mutate an already-shipped version — add a
# new one. (version, human description, fn)
MIGRATIONS = [
    ('0001_backfill_is_shadow_default',
     'students.is_shadow: NULL -> 0 (predates column default)',
     _m_0001_backfill_is_shadow),
    ('0002_backfill_follow_up_completed',
     'notes/communication_logs.follow_up_completed: NULL -> 0',
     _m_0002_backfill_follow_up_completed),
]
