"""The stained-glass outline applied to every pie/doughnut/bar chart.

Static assertions on the JS, for the same reason as the responsive-layout
tests: pytest cannot run Chart.js. What matters here is one invariant that is
easy to break and silently catastrophic — the plugin must never touch line or
radar datasets, because for those `borderColor` IS the plotted line, so forcing
it to the outline colour would paint every series the same and erase the chart.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / 'app' / 'static' / 'js' / 'chart-enhancements.js'
CSS = ROOT / 'app' / 'static' / 'css' / 'style.css'


@pytest.fixture(scope='module')
def js():
    return JS.read_text(encoding='utf-8')


def _lead_types(source):
    m = re.search(r'LEAD_TYPES\s*=\s*\[(.*?)\]', source, re.S)
    assert m, 'LEAD_TYPES list is gone — the outline plugin was removed'
    return {t.strip().strip('\'"') for t in m.group(1).split(',') if t.strip()}


def test_the_outline_applies_to_filled_shape_charts(js):
    assert {'pie', 'doughnut', 'bar'} <= _lead_types(js)


@pytest.mark.parametrize('unsafe', ['line', 'radar', 'scatter', 'bubble'])
def test_the_outline_never_touches_line_style_charts(js, unsafe):
    """borderColor is the line itself on these; overriding it would flatten
    every series into one indistinguishable colour."""
    assert unsafe not in _lead_types(js)


def test_the_plugin_is_registered(js):
    assert 'Chart.register(stainedGlass)' in js


def test_it_reapplies_on_update_not_just_at_creation(js):
    """Charts that call chart.update() rebuild their datasets from the original
    config, so a one-time pass at creation would be undone."""
    block = re.search(r'var stainedGlass\s*=\s*\{(.*?)\n    \};', js, re.S)
    assert block, 'plugin body not found'
    assert 'beforeUpdate' in block.group(1)


def test_it_overrides_per_dataset_colours(js):
    """Most charts in this app pass their own borderColor, which beats
    Chart.defaults.elements.*; the plugin has to write onto the dataset."""
    block = re.search(r'var stainedGlass\s*=\s*\{(.*?)\n    \};', js, re.S)
    body = block.group(1)
    assert 'ds.borderColor' in body and 'ds.borderWidth' in body


def test_a_dataset_may_override_the_chart_type(js):
    """Mixed charts (a line drawn over bars) set `type` per dataset; reading
    only the chart-level type would outline the line dataset too."""
    block = re.search(r'var stainedGlass\s*=\s*\{(.*?)\n    \};', js, re.S)
    assert re.search(r'ds\.type\s*\|\|', block.group(1))


def test_the_outline_colour_is_themeable_with_a_dark_fallback(js):
    assert "tok('--chart-outline'" in js
    assert '--chart-outline' in CSS.read_text(encoding='utf-8')


def test_bars_are_outlined_on_all_four_sides(js):
    """Chart.js skips the base edge by default, which leaves bars looking
    unfinished once the outline is dark enough to notice."""
    assert re.search(r'elements\.bar\.borderSkipped\s*=\s*false', js)
