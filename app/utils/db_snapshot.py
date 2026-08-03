"""Point-in-time database snapshots for irreversible bulk operations.

Extracted from settings.backup() so the same copy logic serves both the manual
Backup button and automatic pre-flight snapshots taken before a bulk mutation.
"""
import os
import shutil
from datetime import datetime, timezone

from config import Config, DATA_DIR


def db_path():
    """Absolute path to the live SQLite database file.

    DATA_DIR is a MODULE-level name in config.py, not a Config attribute, so
    the previous `Config.DATA_DIR if hasattr(...) else 'data'` always took the
    fallback and resolved relative to the working directory — snapshots landed
    somewhere other than the configured data directory.
    """
    return os.path.join(DATA_DIR, 'counselor.db')


def snapshot_database(label='backup'):
    """Copy the database aside, returning the new path (or None on failure).

    Used before operations whose built-in undo is time-boxed. The rollover
    undo, for instance, expires after 24 hours (models/rollover.py) — but a
    rollover runs in June and the mistake tends to surface in August, long
    after the snapshot row is useless. A file copy costs milliseconds and turns
    that 24-hour window into a permanent one.

    Never raises: a failed snapshot must not block the operation itself, and
    callers are expected to log the None.
    """
    src = db_path()
    if not os.path.exists(src):
        return None
    try:
        backup_dir = Config.BACKUP_DIR
        os.makedirs(backup_dir, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        safe_label = ''.join(c for c in label if c.isalnum() or c in '-_') or 'backup'
        dest = os.path.join(backup_dir, f'counselor_{safe_label}_{stamp}.db')
        shutil.copy2(src, dest)
        return dest
    except Exception:
        return None
