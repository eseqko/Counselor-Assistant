"""Lint-via-test: the static theme-clash audit must stay at zero findings.

If a future template adds a hardcoded light background, an unprotected Chart.js
instance, or a compound class+element selector that beats the global glass
override via source order, the audit will catch it and this test will fail.

Run `python scripts/audit_theme_clashes.py` locally to see the report.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

import audit_theme_clashes  # noqa: E402


def test_no_theme_clashes_detected():
    findings = audit_theme_clashes.run_audit()
    if findings:
        # Group for a readable failure message.
        by_cat = {}
        for f in findings:
            by_cat.setdefault(f['category'], []).append(f)
        lines = ['Theme-clash audit detected new findings:']
        for cat in sorted(by_cat):
            rows = by_cat[cat]
            lines.append(f'  Category {cat}: {len(rows)} finding(s)')
            for r in rows[:10]:
                lines.append(f'    {r["path"]}:{r["line"]}  {r["value"]}')
            if len(rows) > 10:
                lines.append(f'    ... and {len(rows) - 10} more')
        lines.append(
            '\nRun `python scripts/audit_theme_clashes.py` for the full list.')
        lines.append(
            'Either add a [data-theme^="glass"] override in app/static/css/themes.css '
            'or extend the ALLOWLIST in scripts/audit_theme_clashes.py with a rationale.')
        raise AssertionError('\n'.join(lines))
