"""Layout invariants for portrait/narrow windows.

These are static assertions on CSS and JS rather than behavioral tests, for the
same reason as tests/test_no_posix_strftime.py: a headless Python suite cannot
observe a browser laying out a page. Each one pins a bug that was real, silent,
and easy to reintroduce — every one of them rendered a 200 OK page.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
STYLE = ROOT / 'app' / 'static' / 'css' / 'style.css'
APP_JS = ROOT / 'app' / 'static' / 'js' / 'app.js'
BASE_HTML = ROOT / 'app' / 'templates' / 'base.html'


@pytest.fixture(scope='module')
def css():
    return STYLE.read_text(encoding='utf-8')


def test_the_hamburger_is_wired_exactly_once():
    """The drawer toggle was bound twice — an inline onclick in base.html AND an
    addEventListener in app.js. Both fired on one click, so the class flipped
    back immediately and the sidebar never opened. Two handlers is the bug.
    """
    pattern = re.compile(r"""getElementById\(['"]sidebar['"]\)\.classList\.toggle|"""
                         r"""sidebar\.classList\.toggle""")
    hits = (len(pattern.findall(BASE_HTML.read_text(encoding='utf-8')))
            + len(pattern.findall(APP_JS.read_text(encoding='utf-8'))))
    assert hits == 1, (
        f'expected exactly one sidebar open-toggle, found {hits}. Two handlers '
        'on the same click cancel out and the drawer stops opening.')


def test_portrait_windows_get_the_drawer(css):
    """A monitor rotated to portrait reports a ~1080px viewport, which is far too
    wide to trip a phone breakpoint — so the sidebar has to key off orientation,
    not width alone, or it keeps its 260px on a screen that cannot spare it.
    """
    assert 'orientation: portrait' in css, 'no orientation-aware rules at all'
    drawer = re.search(
        r'@media\s*\(max-width:\s*768px\)\s*,\s*\(orientation:\s*portrait\)'
        r'[^{]*\{(.*?)\n\}', css, re.S)
    assert drawer, 'the drawer block is no longer shared by narrow AND portrait'
    body = drawer.group(1)
    for rule in ('.sidebar { transform: translateX(-100%); }',
                 '.main-content { margin-left: 0; }',
                 '.menu-toggle { display: block; }'):
        assert rule in body, f'drawer block lost: {rule}'


def test_main_content_can_shrink_below_its_contents(css):
    """.main-content is a flex item, and a flex item defaults to min-width:auto —
    it refuses to shrink below the min-content width of what's inside it. One
    wide table stretched the whole page 85px past the viewport instead of
    scrolling inside its own wrapper.
    """
    rule = re.search(r'\.main-content\s*\{(.*?)\}', css, re.S)
    assert rule, '.main-content rule is gone'
    assert re.search(r'min-width:\s*0', rule.group(1)), (
        '.main-content lost min-width:0 — wide tables will push the page '
        'sideways again instead of scrolling in .table-responsive')


def test_the_backdrop_is_not_matched_with_an_adjacent_sibling(css):
    """base.html puts a <script> between the sidebar and the backdrop, so the
    adjacent-sibling '+' never matched and the dim layer never appeared.
    """
    assert '.sidebar.open ~ .sidebar-backdrop' in css
    assert '.sidebar.open + .sidebar-backdrop' not in css, (
        "'+' skips nothing — a <script> sits between the two elements")


def test_the_profile_grid_reflows_in_portrait(css):
    """Three columns with 260px floors leave the metrics column at its minimum in
    a portrait window; the mid column has to span instead."""
    block = re.search(r'@media\s*\(orientation:\s*portrait\)\s*and\s*'
                      r'\(min-width:\s*\d+px\)\s*\{(.*?)\n\}', css, re.S)
    assert block, 'no portrait rule for .profile-shell'
    assert '.profile-shell' in block.group(1)
    assert 'grid-column: 1 / -1' in block.group(1)


def test_the_profile_header_wraps(css):
    """Avatar + name + badges + prev/next + action buttons overflow a narrow
    window unless the row is allowed to wrap."""
    rule = re.search(r'\.profile-header\s*\{(.*?)\}', css, re.S)
    assert rule and 'flex-wrap: wrap' in rule.group(1)


@pytest.mark.parametrize('template,table_hint', [
    ('analytics/insights.html', 'data-table'),
    ('college_career/student_plan.html', 'mini-table'),
    ('caseload/transcript_batch.html', 'matchTable'),
])
def test_wide_tables_have_a_scroll_wrapper(template, table_hint):
    """These three rendered with no horizontal-scroll container at all, so they
    blew the layout out sideways rather than scrolling."""
    text = (ROOT / 'app' / 'templates' / template).read_text(encoding='utf-8')
    assert table_hint in text, f'{template} no longer contains {table_hint}'
    assert 'table-responsive' in text, (
        f'{template} lost its .table-responsive wrapper')
