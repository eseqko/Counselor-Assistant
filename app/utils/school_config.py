"""Single source of truth for a user's school identity.

The complete identity — schoolName, shortName, mascot, mascotEmoji, motto,
schoolYear, colors{primary,secondary}, logoUrl, contact*, grade_levels,
setupComplete — lives in ``User.school_config_json`` (a JSON blob). The legacy
``User.school_name`` column is kept as a synced mirror of ``schoolName`` so
server-rendered chrome (user menu, export filename) and any code that reads the
column stay correct.

Every read/write of the school identity should go through these two functions
so the JSON blob, the column, and the browser's localStorage copy never drift —
which was the cause of the Course-Catalog-Wiki-vs-main-app desync where a save
from one surface silently dropped fields written by another.

Read:   get_school_config(user)            -> complete dict
Write:  merge_school_config(user, partial)  -> merged dict, column synced
"""
import json


def _is_empty(v):
    if v is None or v == '':
        return True
    if isinstance(v, dict) and not v:
        return True
    if isinstance(v, (list, tuple)) and len(v) == 0:
        return True
    return False


def get_school_config(user):
    """Return ``user``'s complete school-config dict.

    Parses ``school_config_json`` (tolerating bad/missing JSON), backfills
    ``schoolName`` from the ``school_name`` column when the blob doesn't carry
    it, and DERIVES ``setupComplete`` from presence of meaningful identity (a
    school name plus a primary colour) — so a user who set things up through
    any surface (main-app wizard, profile form, settings import) is treated as
    "configured" by the Catalog Wiki view, which gates on that flag. Without
    this derivation the in-app catalog iframe sent users back to setup even
    though they'd already provided everything it needs.
    """
    cfg = {}
    raw = getattr(user, 'school_config_json', None)
    if raw:
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                cfg = loaded
        except (ValueError, TypeError):
            cfg = {}
    if not cfg.get('schoolName') and getattr(user, 'school_name', None):
        cfg['schoolName'] = user.school_name
    # Only DERIVE the flag — never overwrite an explicit False (e.g. a user
    # who deliberately reset setup in the catalog form).
    if 'setupComplete' not in cfg:
        has_name = bool(cfg.get('schoolName'))
        has_colour = bool((cfg.get('colors') or {}).get('primary'))
        if has_name and has_colour:
            cfg['setupComplete'] = True
    return cfg


def merge_school_config(user, partial, commit=True):
    """Merge ``partial`` into ``user``'s stored school config and persist.

    Merge semantics, chosen to make cross-surface saves safe:

    * Keys PRESENT in ``partial`` win — including empty values, so a surface can
      legitimately clear a field it owns (e.g. removing a logo sets logoUrl='').
    * Keys ABSENT from ``partial`` are PRESERVED — so a save from a surface that
      doesn't know about a field (the Catalog Wiki has no 'grade_levels'; the
      main-app wizard has no 'mascot') never drops it. This is the core fix.
    * ``colors`` merges per sub-key with only non-empty values applied, so
      sending just {primary} never drops 'secondary' and an empty colour never
      wipes a real one.

    Keeps ``user.school_name`` synced with the merged ``schoolName``. Commits by
    default; pass ``commit=False`` when the caller manages the transaction.
    Returns the merged dict.
    """
    from app import db

    cfg = get_school_config(user)
    if isinstance(partial, dict):
        for k, v in partial.items():
            if k == 'colors' and isinstance(v, dict):
                merged = dict(cfg.get('colors') or {})
                for ck, cv in v.items():
                    if not _is_empty(cv):
                        merged[ck] = cv
                cfg['colors'] = merged
            else:
                cfg[k] = v

    if cfg.get('schoolName'):
        user.school_name = cfg['schoolName']
    user.school_config_json = json.dumps(cfg, ensure_ascii=False)

    if commit:
        db.session.commit()
    return cfg
