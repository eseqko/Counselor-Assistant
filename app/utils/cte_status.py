"""CTE Concentrator/Completer status computation.

Computes dual-track status (District + Perkins V) from cte_courses_json.
Falls back to credit thresholds when course-level data is unavailable.

Why both labels:
- The federal Perkins V definition requires 2+ courses in the same pathway
  for Concentrator status, and a capstone for Completer. This is what
  CALPADS expects.
- Many CA districts (including this one) use 2-course pathways where the
  first course is labeled "introductory/concentrator" and the second is
  the "capstone". Their counselors think of a student as a Concentrator
  after one course and a Completer after two. The District label
  preserves that mental model.

Returning both lets counselors see at a glance which one applies.
"""


CREDIT_FALLBACK_LEVELS = [
    ('Explorer',     5),
    ('Concentrator', 10),
    ('Completer',    15),
    ('Advanced',     20),
]


def compute_cte_status(cte_courses, cte_completed_credits=0):
    """Return CTE status dict from cte_courses_json data.

    Args:
        cte_courses: dict like {'pathway': str, 'courses': [{'name','level',...}]}
                     or None.
        cte_completed_credits: total CTE credits, used as fallback when
                               course-level data is missing.

    Returns dict with keys:
        pathway          (str | None)
        course_count     (int)
        has_capstone     (bool)
        district_status  (str)  — 'None' | 'Participant' | 'Concentrator' | 'Completer'
        perkins_status   (str)  — same vocabulary
        source           (str)  — 'courses' or 'credits' (fallback)
    """
    if not cte_courses or not cte_courses.get('courses'):
        fb_level = 'None'
        for name, cred_min in reversed(CREDIT_FALLBACK_LEVELS):
            if cte_completed_credits >= cred_min:
                fb_level = name
                break
        return {
            'pathway': None,
            'course_count': 0,
            'has_capstone': False,
            'district_status': fb_level,
            'perkins_status': fb_level,
            'source': 'credits',
        }

    pathway = cte_courses.get('pathway') or None
    courses = [c for c in cte_courses.get('courses', []) if c.get('name')]
    levels = [(c.get('level') or '').strip().lower() for c in courses]
    course_count = len(courses)
    has_capstone = any(lvl == 'capstone' for lvl in levels)
    has_intro_or_concentrator = any(lvl in ('introductory', 'concentrator') for lvl in levels)

    if course_count == 0:
        district = 'None'
    elif has_capstone:
        district = 'Completer'
    elif has_intro_or_concentrator:
        district = 'Concentrator'
    else:
        # Courses present but no levels assigned — district can't promote yet
        district = 'Participant'

    if course_count == 0:
        perkins = 'None'
    elif course_count == 1:
        perkins = 'Participant'
    elif has_capstone:
        perkins = 'Completer'
    else:
        perkins = 'Concentrator'

    return {
        'pathway': pathway,
        'course_count': course_count,
        'has_capstone': has_capstone,
        'district_status': district,
        'perkins_status': perkins,
        'source': 'courses',
    }
