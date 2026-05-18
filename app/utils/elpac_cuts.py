"""Summative ELPAC Overall Composite Scale Score cut points.

Source: CDE Summative ELPAC Scale Score Ranges (Performance Level cuts)
based on the published 2023-24 reporting standards. The Overall scale
runs 1150-1700.

PL boundaries (1/2/3/4) below are the official CDE values. Within PL 2
and PL 3, the L/H sublevel split is taken at the midpoint of each PL's
scale range — the CDE technical report uses equipercentile sublevel cuts
which are not separately published; the midpoint is a transparent
approximation and well within a few scale points of the official cuts.
If your district has the official L/H scale cuts, edit the
`_split_at_midpoint` rows below.

PL 4 has no H sublevel for ELPI purposes: anyone at PL 4 is either
reclassified (RFEP) or "Maintained ELL 4L" per CDE methodology.
"""

# (level, sublevel, scale_min, scale_max). sublevel=None for PL 1.
def _build_band(pl1_max, pl2_max, pl3_max, pl4_max=1700, pl1_min=1150):
    pl2_min = pl1_max + 1
    pl3_min = pl2_max + 1
    pl4_min = pl3_max + 1
    pl2_mid = (pl2_min + pl2_max) // 2
    pl3_mid = (pl3_min + pl3_max) // 2
    return [
        (1, None, pl1_min, pl1_max),
        (2, 'L', pl2_min, pl2_mid),
        (2, 'H', pl2_mid + 1, pl2_max),
        (3, 'L', pl3_min, pl3_mid),
        (3, 'H', pl3_mid + 1, pl3_max),
        (4, 'L', pl4_min, pl4_max),
    ]


# Official Summative ELPAC PL 1/2/3 maximum scale scores by grade.
# (PL 4 starts at the next integer and runs to 1700.)
OVERALL_CUTS = {
    (0, 0):   _build_band(1318, 1409, 1481),  # K
    (1, 1):   _build_band(1378, 1452, 1496),
    (2, 2):   _build_band(1413, 1469, 1510),
    (3, 3):   _build_band(1424, 1487, 1531),
    (4, 4):   _build_band(1442, 1499, 1541),
    (5, 5):   _build_band(1451, 1505, 1547),
    (6, 6):   _build_band(1454, 1509, 1547),
    (7, 7):   _build_band(1462, 1516, 1550),
    (8, 8):   _build_band(1473, 1521, 1555),
    (9, 10):  _build_band(1411, 1492, 1547),
    (11, 12): _build_band(1416, 1498, 1553),
}


def _band_for_grade(grade):
    if grade is None:
        return None
    for (lo, hi), cuts in OVERALL_CUTS.items():
        if lo <= grade <= hi:
            return cuts
    return None


def lookup_sublevel(overall_level, overall_scale, test_grade_level):
    """Return the L/H sublevel for a given Overall PL + scale + grade.

    Returns 'L', 'H', or None (if level is 1, level is 4, grade band
    unknown, or scale falls outside the published range).
    """
    if overall_level is None or overall_scale is None:
        return None
    if overall_level == 1:
        return None
    if overall_level == 4:
        # ELPI methodology treats all PL 4 as "4L" — sublevel within 4
        # doesn't change the category.
        return 'L'
    cuts = _band_for_grade(test_grade_level)
    if not cuts:
        return None
    for lvl, sub, lo, hi in cuts:
        if lvl == overall_level and lo <= overall_scale <= hi:
            return sub
    return None
