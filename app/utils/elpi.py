"""English Learner Progress Indicator (ELPI) computation.

Implements two variants of the CDE Dashboard ELPI:
  - Simplified: uses only Overall PL (1-4). Categories: Decreased,
    Maintained 1-2, Maintained 3, Maintained 4, Progressed, Reclassified.
  - Full: uses Overall PL with L/H sublevels per CDE methodology.
    Categories: Decreased, Maintained ELL 1/2L/2H, Maintained ELL 3L/3H,
    Maintained ELL 4L, Progressed, Reclassified.

Both versions need a current score, a prior score (or None), and the
student's current EL status to detect Reclassified.
"""
from app.utils.elpac_cuts import lookup_sublevel


# Ordering used to compare two ELPI levels. Lower index = lower proficiency.
# 'R' represents Reclassified (above all EL levels).
_ELPI_ORDER = ['1', '2L', '2H', '3L', '3H', '4L', 'R']
_ELPI_RANK = {lvl: i for i, lvl in enumerate(_ELPI_ORDER)}


def elpi_rank(level_str):
    """Return the integer rank of an ELPI level string ('1', '2L', ... 'R'),
    or None if unrecognized. Used for measuring level jumps.
    """
    return _ELPI_RANK.get(level_str)


def _format_elpi_level(overall_level, sublevel):
    if overall_level is None:
        return None
    if overall_level == 1:
        return '1'
    if sublevel:
        return f'{overall_level}{sublevel}'
    # PL 2/3/4 with no scale data — fall back to numeric only
    return str(overall_level)


def _elpi_level_from_score(score):
    """Return ELPI level string (e.g., '2L') from an ELPACScore row, or None."""
    if score is None or score.overall_level is None:
        return None
    sub = lookup_sublevel(score.overall_level, score.overall_scale, score.test_grade_level)
    return _format_elpi_level(score.overall_level, sub)


def compute_elpi(current_score, prior_score, current_el_status):
    """Compute both simplified and full ELPI status for one student.

    Args:
        current_score: latest Summative ELPACScore (or None)
        prior_score: prior-year Summative ELPACScore (or None)
        current_el_status: student.el_status string ('RFEP', 'Newcomer', 'LTEL', 'EO')

    Returns dict with:
        pl_now, pl_prior          (int 1-4 or None)
        elpi_now, elpi_prior      (str like '2L' or None)
        simplified_status         (str)
        full_status               (str)
        is_reclassified           (bool)
        is_new_at_4               (bool — scored 4 this year, was <4 last year)
    """
    pl_now = current_score.overall_level if current_score else None
    pl_prior = prior_score.overall_level if prior_score else None
    elpi_now = _elpi_level_from_score(current_score)
    elpi_prior = _elpi_level_from_score(prior_score)

    is_reclassified = (current_el_status == 'RFEP')
    is_new_at_4 = (pl_now == 4 and pl_prior is not None and pl_prior < 4)

    # --- Simplified status (uses PL 1-4 only) ---
    if is_reclassified:
        simplified_status = 'Reclassified'
    elif pl_now is None:
        simplified_status = 'No current score'
    elif pl_prior is None:
        simplified_status = 'No prior score'
    elif pl_now > pl_prior:
        simplified_status = 'Progressed'
    elif pl_now < pl_prior:
        simplified_status = 'Decreased'
    else:
        # Maintained — bucket by current PL
        if pl_now in (1, 2):
            simplified_status = 'Maintained 1-2'
        elif pl_now == 3:
            simplified_status = 'Maintained 3'
        else:
            simplified_status = 'Maintained 4'

    # --- Full status (uses sublevels) ---
    if is_reclassified:
        full_status = 'Reclassified'
    elif elpi_now is None:
        full_status = 'No current score'
    elif elpi_prior is None:
        full_status = 'No prior score'
    else:
        now_rank = _ELPI_RANK.get(elpi_now)
        prior_rank = _ELPI_RANK.get(elpi_prior)
        if now_rank is None or prior_rank is None:
            # Can't determine sublevel — fall back to PL comparison
            if pl_now > pl_prior:
                full_status = 'Progressed'
            elif pl_now < pl_prior:
                full_status = 'Decreased'
            else:
                full_status = f'Maintained ELL {elpi_now}'
        elif now_rank > prior_rank:
            full_status = 'Progressed'
        elif now_rank < prior_rank:
            full_status = 'Decreased'
        else:
            if elpi_now in ('1', '2L', '2H'):
                full_status = 'Maintained ELL 1-2H'
            elif elpi_now in ('3L', '3H'):
                full_status = 'Maintained ELL 3L-3H'
            elif elpi_now == '4L':
                full_status = 'Maintained ELL 4L'
            else:
                full_status = f'Maintained ELL {elpi_now}'

    return {
        'pl_now': pl_now,
        'pl_prior': pl_prior,
        'elpi_now': elpi_now,
        'elpi_prior': elpi_prior,
        'simplified_status': simplified_status,
        'full_status': full_status,
        'is_reclassified': is_reclassified,
        'is_new_at_4': is_new_at_4,
    }


# Category lists for stable iteration order in templates / charts.
SIMPLIFIED_CATEGORIES = [
    'Decreased',
    'Maintained 1-2',
    'Maintained 3',
    'Maintained 4',
    'Progressed',
    'Reclassified',
]

FULL_CATEGORIES = [
    'Decreased',
    'Maintained ELL 1-2H',
    'Maintained ELL 3L-3H',
    'Maintained ELL 4L',
    'Progressed',
    'Reclassified',
]
