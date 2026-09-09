"""Cleanup helpers for per-user PII stored in JSON sidecar files.

Follow-ups, communication templates, and mail-merge letter templates live in
flat JSON files under DATA_DIR, scoped only by an integer ``counselor_id``.
Because ``users.id`` is a reusable SQLite rowid, an entry left behind after its
owner is deleted (or after a factory reset) is silently inherited by the next
account that is assigned the same id — leaking a departed counselor's student
names, IDs, and free-text notes to someone who was never on that caseload.
Purge these stores whenever a user is deleted or the app is reset.
"""
import json
import os

from config import DATA_DIR

# Flat JSON stores of student PII — each a list of dicts carrying counselor_id.
PII_SIDECAR_FILES = ('followups.json', 'comm_templates.json', 'letter_templates.json')
# Write-only orphan store (AI-tools email drafts) that no route reads back.
ORPHAN_SIDECAR_FILES = ('email_custom_templates.json',)


def _purge_entries(name, counselor_id):
    """Drop entries with this counselor_id from one list-of-dicts JSON store."""
    path = os.path.join(DATA_DIR, name)
    if not os.path.exists(path):
        return 0
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return 0
    if not isinstance(data, list):
        return 0
    kept = [e for e in data if e.get('counselor_id') != counselor_id]
    if len(kept) != len(data):
        try:
            with open(path, 'w') as f:
                json.dump(kept, f, indent=2, default=str)
        except OSError:
            return 0
    return len(data) - len(kept)


def purge_counselor_followups(counselor_id):
    """Remove only the counselor's follow-ups (student names/IDs/notes).

    Used by the caseload reset: the follow-ups are student data, but the same
    counselor's communication and letter templates are their own authored
    content and must survive a caseload reset. Returns entries removed.
    """
    return _purge_entries('followups.json', counselor_id)


def purge_counselor_sidecars(counselor_id):
    """Remove every JSON-sidecar entry owned by ``counselor_id``.

    Call on user deletion so a departed counselor's follow-ups/templates can't
    be inherited by a later account that reuses the same integer id. Returns the
    number of entries removed. Never raises.
    """
    removed = 0
    for name in PII_SIDECAR_FILES:
        removed += _purge_entries(name, counselor_id)
    return removed


def delete_all_sidecars():
    """Delete every JSON-sidecar PII store outright (used by factory reset)."""
    for name in PII_SIDECAR_FILES + ORPHAN_SIDECAR_FILES:
        path = os.path.join(DATA_DIR, name)
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
