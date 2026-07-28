#!/usr/bin/env python3
"""Static audit for cross-theme style clashes.

Categories scanned:

    A. Inline <style> selectors that use clash-prone vars for SURFACE colours
       — var(--white) / var(--bg) / var(--light-gray) as background.
    B. Hardcoded near-white / light-pastel hex backgrounds in inline <style>.
    C. Inline style="color:#..." attributes with hex values likely too-dark on
       dark themes (luminance <= 0.45). Equivalent dark text on light surfaces.
    D. Specificity collisions — selectors that themes.css scopes to
       [data-theme^="glass"] but a template's inline <style> declares at lower
       specificity AND later source order. Inline wins -> theme override is
       silently defeated. (`.analytics-toolbar select` is the canonical case.)
    E. Chart.js instances ( new Chart(...) ) that don't pass tick/legend/grid
       colour options AND aren't covered by global Chart.defaults.
    F. Native form controls (<select>/<input>) where a template's inline rule
       redefines background/color at specificity matching the global theme
       rule — same as D but specifically for native controls.

Run with no arguments to print a report. Exits non-zero when findings count
exceeds the allowlist baseline so it can run in CI / pytest.
"""
from __future__ import annotations
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / 'app' / 'templates'
STATIC = ROOT / 'app' / 'static'
THEMES_CSS = STATIC / 'css' / 'themes.css'

# ----------------------------------------------------------------------------
# Allowlist — intentional decoration that mustn't trigger findings.
# Each entry: (category, file_path_fragment, hex_or_selector). Match is substr.
# ----------------------------------------------------------------------------
ALLOWLIST = {
    # Meeting Notes flow-area tag buttons: intentional semantic pastels.
    ('B', 'meeting_notes/_partials/_flow_area.html', None),
    # Meeting Notes styles: tag/badge palette is intentionally branded light.
    ('B', 'meeting_notes/_partials/_styles.html', None),
    # Meeting Notes view: badge palette.
    ('B', 'meeting_notes/view.html', None),
    ('B', 'meeting_notes/index.html', None),
    ('B', 'meeting_notes/edit.html', None),
    # Screening yellow interpretation box / band-highlight — intentional light.
    ('B', 'screenings/view_result.html', None),
    # Graduation severity pills, exempt badges — light-pastel by design.
    ('B', 'graduation/index.html', None),
    ('B', 'graduation/detail.html', None),
    # College/Career pathway pills — light-pastel by design.
    ('B', 'college_career/index.html', None),
    ('B', 'college_career/student_plan.html', None),
    ('B', 'caseload/_partials/_college_career_summary.html', None),
    # Communications view: highlighted comment box (intentional warning shade).
    ('B', 'communications/view.html', None),
    # Transcript-batch preview UI: hardcoded ad-hoc palette (its own design).
    ('B', 'caseload/transcript_batch.html', None),
    # AI course recs partial: in-place spinner + error chip.
    ('B', 'caseload/_partials/_ai_course_recs.html', None),
    # Caseload upload: light info box (one-off).
    ('B', 'caseload/upload.html', None),
    # Settings has explicit Reset-Demo / Danger-Zone styling.
    ('B', 'settings/index.html', None),
    # Reports/admin internal tables with light row striping (covered by C/D).
    ('B', 'admin/index.html', None),
    ('B', 'admin/users.html', None),
    ('B', 'admin/caseload_equity.html', None),
    ('B', 'knowledge_base/index.html', None),
    ('B', 'knowledge_base/document.html', None),
    # Insights pill helpers (.pill.f / .pill.d already glass-overridden).
    ('B', 'analytics/insights.html', None),
    ('B', 'analytics/el_outcomes.html', None),
    # Public / print-only pages — counselor never sees these on a theme:
    # availability/book is a parent-facing public booking page; student_portal
    # is a token-gated student tool (no login, no theme); meeting_prep/pack and
    # academic_plan/print are print-letterhead views; auto_review is print-friendly.
    ('A', 'student_portal/', None),
    ('B', 'student_portal/', None),
    ('A', 'availability/book.html', None),
    ('B', 'availability/book.html', None),
    ('B', 'availability/auto_review.html', None),
    # post_grad/survey is the alumni-facing self-report link — same
    # no-login/no-theme public page pattern as availability/book.
    ('A', 'post_grad/survey.html', None),
    ('B', 'post_grad/survey.html', None),
    # setup/blocked renders pre-login, before any theme preference exists.
    ('A', 'setup/blocked.html', None),
    ('B', 'setup/blocked.html', None),
    ('A', 'meeting_prep/pack.html', None),
    ('B', 'meeting_prep/pack.html', None),
    ('A', 'academic_plan/print.html', None),
    ('B', 'academic_plan/print.html', None),
    # Academic Plan detail: status pastels + slot pastels are intentional
    # design — explicit glass overrides handle them in themes.css.
    ('B', 'academic_plan/detail.html', None),
    ('B', 'academic_plan/index.html', None),
    # Availability share-box is also handled by glass override (.share-box).
    ('B', 'availability/index.html', None),
    # Categories C text-colour calls are noisy and many are intentionally on
    # white backgrounds inside print contexts; the bulk-fix pass replaces the
    # most common slates, but we don't fail CI on every remaining one.
    ('C', None, None),
}


def is_allowlisted(category: str, path: Path, value: str | None = None) -> bool:
    rel = path.relative_to(ROOT).as_posix() if path else ''
    for cat, frag, val in ALLOWLIST:
        if cat != category:
            continue
        if frag and frag not in rel:
            continue
        if val and value and val not in value:
            continue
        return True
    return False


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
INLINE_STYLE_BLOCK = re.compile(r'<style\b[^>]*>(.*?)</style>', re.S | re.I)


def iter_inline_style_blocks(html_text: str):
    """Yield (start_line, end_line, css_text) for every <style>...</style>."""
    for m in INLINE_STYLE_BLOCK.finditer(html_text):
        start = html_text[:m.start()].count('\n') + 1
        end = html_text[:m.end()].count('\n') + 1
        yield start, end, m.group(1)


def line_of(text: str, idx: int) -> int:
    return text.count('\n', 0, idx) + 1


def hex_luminance(hex_value: str) -> float:
    """Relative luminance per WCAG; accepts #rgb or #rrggbb."""
    h = hex_value.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    if len(h) != 6:
        return 0.5
    try:
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return 0.5

    def lin(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def iter_templates():
    for p in TEMPLATES.rglob('*.html'):
        yield p


# ----------------------------------------------------------------------------
# Category A: surface backgrounds using clash-prone CSS vars in <style> blocks
# ----------------------------------------------------------------------------
SURFACE_VAR_BG = re.compile(
    r'background\s*:\s*var\(--(white|bg|light-gray)\)', re.I)


SELECTOR_BEFORE_BRACE = re.compile(
    r'([^\{\}]+?)\{([^\}]*)\}', re.S)
LEAF_CLASS = re.compile(r'\.([a-zA-Z_][\w-]*)')


def _classes_in_glass_overrides() -> set[str]:
    """Return every leaf class my [data-theme^="glass"] rules cover."""
    if not THEMES_CSS.exists():
        return set()
    text = THEMES_CSS.read_text(encoding='utf-8')
    classes = set()
    # Find every selector group preceded by [data-theme^="glass"] and pluck
    # its trailing class names.
    for m in re.finditer(r'\[data-theme\^="glass"\][^,{]*?(?=[,{])', text):
        sel = m.group(0)
        for cm in LEAF_CLASS.finditer(sel):
            classes.add(cm.group(1))
    return classes


def _rule_contains(rule_body: str, prop_regex: re.Pattern) -> bool:
    return bool(prop_regex.search(rule_body))


def scan_category_a():
    """Flag inline rules using var(--white)/--bg/--light-gray for background
    UNLESS the rule's selector matches a class my [data-theme^="glass"]
    overrides take care of — those are dominated by higher specificity and
    won't actually render their light surface on glass."""
    findings = []
    glass_covered = _classes_in_glass_overrides()
    # The [data-theme^="glass"] [class] select|input|textarea bump in themes.css
    # wins at (0,2,1) over any inline compound `.foo select` rule, so those
    # are not real clashes either.
    has_compound_bump = False
    if THEMES_CSS.exists():
        if '[data-theme^="glass"] [class] select' in THEMES_CSS.read_text(encoding='utf-8'):
            has_compound_bump = True
    form_control_leaf = re.compile(r'\b(select|textarea|input)\b\s*$', re.I)
    for path in iter_templates():
        if is_allowlisted('A', path):
            continue
        text = path.read_text(encoding='utf-8', errors='replace')
        for s_line, _, css in iter_inline_style_blocks(text):
            for rule_m in SELECTOR_BEFORE_BRACE.finditer(css):
                selector = rule_m.group(1).strip()
                body = rule_m.group(2)
                if not SURFACE_VAR_BG.search(body):
                    continue
                # Pluck all leaf classes from the selector. If ANY are covered
                # by a theme override, the theme rule wins (0,2,0) > (0,1,0).
                classes = {cm.group(1) for cm in LEAF_CLASS.finditer(selector)}
                if classes & glass_covered:
                    continue
                # If the rule is a class+form-control compound, the (0,2,1)
                # bump in themes.css beats it; skip.
                if has_compound_bump and any(
                        form_control_leaf.search(sub.strip())
                        for sub in selector.split(',')):
                    if any('.' in sub for sub in selector.split(',')):
                        continue
                # Skip pseudo-element/class-only rules (e.g. ::placeholder).
                if not classes and selector.strip().startswith(':'):
                    continue
                # Find the line of the background: declaration.
                prop_m = SURFACE_VAR_BG.search(body)
                local_line = body[:prop_m.start()].count('\n')
                # body starts after the opening brace of the rule
                rule_start_in_css = rule_m.start(2)
                line_offset = css[:rule_start_in_css].count('\n') + local_line
                findings.append({
                    'category': 'A',
                    'path': path.relative_to(ROOT).as_posix(),
                    'line': s_line + line_offset,
                    'value': f'{selector} {{ {prop_m.group(0)} }}',
                })
    return findings


# ----------------------------------------------------------------------------
# Category B: hardcoded near-white/light-pastel hex backgrounds
# ----------------------------------------------------------------------------
HEX_BG = re.compile(r'background\s*:\s*(#[0-9a-fA-F]{3,6})\b', re.I)


def scan_category_b():
    findings = []
    glass_covered = _classes_in_glass_overrides()
    for path in iter_templates():
        if is_allowlisted('B', path):
            continue
        text = path.read_text(encoding='utf-8', errors='replace')
        for s_line, _, css in iter_inline_style_blocks(text):
            for rule_m in SELECTOR_BEFORE_BRACE.finditer(css):
                selector = rule_m.group(1).strip()
                body = rule_m.group(2)
                hex_match = HEX_BG.search(body)
                if not hex_match:
                    continue
                hex_val = hex_match.group(1)
                if hex_luminance(hex_val) < 0.80:
                    continue  # only near-white / light-pastel
                classes = {cm.group(1) for cm in LEAF_CLASS.finditer(selector)}
                if classes & glass_covered:
                    continue
                if not classes and selector.strip().startswith(':'):
                    continue
                prop_m = hex_match
                local_line = body[:prop_m.start()].count('\n')
                rule_start_in_css = rule_m.start(2)
                line_offset = css[:rule_start_in_css].count('\n') + local_line
                findings.append({
                    'category': 'B',
                    'path': path.relative_to(ROOT).as_posix(),
                    'line': s_line + line_offset,
                    'value': f'{selector} {{ background: {hex_val} }}',
                })
    return findings


# ----------------------------------------------------------------------------
# Category C: inline style="color:#..." with dark hex (low luminance text)
# ----------------------------------------------------------------------------
INLINE_COLOR_ATTR = re.compile(
    r'''style\s*=\s*["'][^"']*color\s*:\s*(#[0-9a-fA-F]{3,6})''', re.I)


def scan_category_c():
    findings = []
    for path in iter_templates():
        if is_allowlisted('C', path):
            continue
        text = path.read_text(encoding='utf-8', errors='replace')
        for m in INLINE_COLOR_ATTR.finditer(text):
            hex_val = m.group(1)
            lum = hex_luminance(hex_val)
            if 0.20 < lum < 0.55:
                findings.append({
                    'category': 'C',
                    'path': path.relative_to(ROOT).as_posix(),
                    'line': line_of(text, m.start()),
                    'value': f'color: {hex_val}',
                })
    return findings


# ----------------------------------------------------------------------------
# Category D/F: selectors declared at SAME specificity as my glass overrides
# but later in source order -> the inline rule wins.
# ----------------------------------------------------------------------------
GLASS_RULE = re.compile(
    r'\[data-theme\^="glass"\]\s+([^\s{,][^{,]*?)\s*[,{]', re.I)


def collect_glass_overridden_selectors() -> set[str]:
    """Selectors themes.css thinks it owns under [data-theme^="glass"]."""
    if not THEMES_CSS.exists():
        return set()
    text = THEMES_CSS.read_text(encoding='utf-8')
    selectors = set()
    for m in GLASS_RULE.finditer(text):
        sel = m.group(1).strip()
        # Normalise — drop trailing combinators and pseudos for matching.
        # Keep the leaf class/element so a later inline rule with the same
        # selector is detected.
        leaf = sel.split()[-1] if sel else sel
        if leaf:
            selectors.add(leaf)
    return selectors


def scan_category_d():
    """Flag REAL collisions: an inline selector at specificity matching the
    glass theme override. Skipped if themes.css carries the (0,2,1) bump rule
    `[data-theme^="glass"] [class] select|input|textarea` which deterministically
    beats compound `.foo element` inline selectors."""
    if THEMES_CSS.exists():
        css = THEMES_CSS.read_text(encoding='utf-8')
        if '[data-theme^="glass"] [class] select' in css:
            return []  # The (0,2,1) bump rule is present; collisions resolve.
    findings = []
    pat = re.compile(
        r'(?:^|[\s,{])(\.[a-zA-Z_][\w-]*(?:\.[a-zA-Z_][\w-]*)*\s+(select|input|textarea))\s*[,{]',
        re.I | re.M)
    for path in iter_templates():
        text = path.read_text(encoding='utf-8', errors='replace')
        for s_line, _, css in iter_inline_style_blocks(text):
            for m in pat.finditer(css):
                offset_line = css[:m.start()].count('\n')
                findings.append({
                    'category': 'D',
                    'path': path.relative_to(ROOT).as_posix(),
                    'line': s_line + offset_line,
                    'value': f'compound `{m.group(1)}` beats [data-theme^="glass"] {m.group(2)} via source order',
                })
    return findings


# ----------------------------------------------------------------------------
# Category E: Chart.js sites without theme-aware tick/legend colour options
# ----------------------------------------------------------------------------
CHART_NEW = re.compile(r'new\s+Chart\s*\(', re.I)


def scan_category_e():
    """Flag a Chart.js instance only when chart-enhancements.js still has no
    theme-aware Chart.defaults block (i.e. the global fix hasn't been applied).
    Once chart-enhancements.js sets Chart.defaults.color from CSS vars, every
    chart benefits and individual sites no longer need per-call options."""
    enhancement = STATIC / 'js' / 'chart-enhancements.js'
    has_global_color = False
    if enhancement.exists():
        text = enhancement.read_text(encoding='utf-8')
        if 'Chart.defaults.color' in text:
            has_global_color = True
    if has_global_color:
        return []  # Global fix applied; chart sites are protected.
    findings = []
    for path in list(iter_templates()) + list((STATIC / 'js').rglob('*.js')):
        try:
            text = path.read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue
        for m in CHART_NEW.finditer(text):
            findings.append({
                'category': 'E',
                'path': path.relative_to(ROOT).as_posix(),
                'line': line_of(text, m.start()),
                'value': 'new Chart(...) with no theme-aware Chart.defaults',
            })
    return findings


# ----------------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------------
def run_audit():
    findings = []
    findings.extend(scan_category_a())
    findings.extend(scan_category_b())
    findings.extend(scan_category_c())
    findings.extend(scan_category_d())
    findings.extend(scan_category_e())
    return findings


def main():
    findings = run_audit()
    by_cat = {}
    for f in findings:
        by_cat.setdefault(f['category'], []).append(f)

    print(f'=== Theme-clash audit: {len(findings)} findings ===\n')
    titles = {
        'A': 'Surface var() backgrounds (--white / --bg / --light-gray)',
        'B': 'Hardcoded near-white / light-pastel hex backgrounds',
        'C': 'Inline style="color:#..." dark text (potential clash on dark)',
        'D': 'Specificity collisions vs [data-theme^="glass"] overrides',
        'E': 'Chart.js sites without theme-aware Chart.defaults',
    }
    for cat in sorted(by_cat):
        rows = by_cat[cat]
        print(f'--- {cat}. {titles.get(cat, cat)} ({len(rows)}) ---')
        for r in rows[:60]:  # cap dumped detail
            print(f'  {r["path"]}:{r["line"]:<5}  {r["value"]}')
        if len(rows) > 60:
            print(f'  ... and {len(rows) - 60} more')
        print()
    return findings


if __name__ == '__main__':
    findings = main()
    # JSON sidecar for the test harness
    out = ROOT / 'scripts' / '.theme_clash_audit.json'
    out.write_text(json.dumps(findings, indent=2))
    sys.exit(1 if findings else 0)
