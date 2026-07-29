"""Check a student's schedule: is it complete, and are prerequisites met?

Two questions a counselor asks on day one.

**Completeness.** On a 4x4 block each academic period holds a course every
quarter, so a full year is 4 periods x 4 quarters = 8 semester-length classes.
Non-credit placements — Early Release, Late Arrival, Mid-Year Grad — still
OCCUPY a period, so they count toward a full schedule while contributing no
credit. A hole in the grid is the finding: "period 3 has nothing in Q4".

**Prerequisites, with 4x4 ordering.** This is the subtle part. On a block
schedule a prerequisite can be taken in Q1-Q2 of the SAME year as the course it
unlocks in Q3-Q4, so it is not enough to look at prior years. Every completed
course is placed on a (school_year, quarter) timeline and a prerequisite counts
if it was passed STRICTLY BEFORE the term the dependent course starts.

A prerequisite that is only *scheduled* earlier this year — not yet graded —
is reported separately as "in progress" rather than as a violation: the student
hasn't failed anything, but it is worth re-checking at the semester break.
"""
from collections import defaultdict

from app.utils.prereq import grade_at_least, rules_from_json

# Placements that fill a period without earning credit. Matched on the title
# because that is how they arrive in the Synergy export.
NON_CREDIT_TITLE_KEYWORDS = (
    'early release', 'late arrival', 'mid-year grad', 'mid year grad',
    'midyear grad', 'work experience release', 'off campus', 'off-campus',
    'independent study release', 'released',
)

TERM_ORDER = {'YR': 0, 'Q1': 1, 'Q2': 2, 'Q3': 3, 'Q4': 4}
ACADEMIC_QUARTERS = ('Q1', 'Q2', 'Q3', 'Q4')

# 4 academic periods x 2 semester-length slots. Configurable per school.
DEFAULT_EXPECTED_CLASSES = 8


def is_non_credit_title(title):
    low = (title or '').strip().lower()
    return any(k in low for k in NON_CREDIT_TITLE_KEYWORDS)


def term_key(school_year, term):
    """Sortable position on the school timeline.

    'YR' sorts to 0 so a year-long course is treated as starting with the year —
    it cannot rely on anything taken later in the same year.
    """
    return (school_year or '', TERM_ORDER.get((term or '').upper(), 9))


def analyze_completeness(entries, expected_classes=DEFAULT_EXPECTED_CLASSES):
    """Is every academic period filled every quarter?

    ``entries`` — ScheduleEntry rows for ONE student-year.
    """
    academic = [e for e in entries if not e.is_non_class and not e.is_advisory]
    periods = sorted({e.period for e in academic if e.period is not None})

    filled = defaultdict(set)          # period -> {quarters covered}
    for e in academic:
        if e.period is None:
            continue
        term = (e.term or '').upper()
        if term == 'YR':
            filled[e.period].update(ACADEMIC_QUARTERS)
        elif term in TERM_ORDER:
            filled[e.period].add(term)

    gaps = []
    for period in periods:
        for quarter in ACADEMIC_QUARTERS:
            if quarter not in filled[period]:
                gaps.append({'period': period, 'term': quarter})

    # A "class" is a semester-length slot: two quarters. Count quarter-slots
    # filled and halve, so a 10-credit two-quarter course counts once and two
    # 5-credit single-quarter courses in the same period also count once
    # between them.
    quarter_slots = sum(len(q) for q in filled.values())
    classes = quarter_slots / 2.0

    non_credit = [e for e in academic if is_non_credit_title(e.course_title)]

    return {
        'periods': periods,
        'gaps': gaps,
        'classes': classes,
        'expected_classes': expected_classes,
        'is_complete': not gaps and classes >= expected_classes,
        'non_credit_entries': non_credit,
        'grid': {p: sorted(filled[p], key=lambda t: TERM_ORDER[t]) for p in periods},
    }


def build_completion_timeline(grade_records):
    """course_number -> best (term_key, letter_grade) the student earned.

    Keeps the EARLIEST passing attempt so a retake doesn't push a prerequisite
    later than it was actually satisfied, and the best grade at that point.
    """
    timeline = defaultdict(list)
    for g in grade_records:
        if not g.course_number or not g.letter_grade:
            continue
        quarter = f'Q{g.quarter}' if g.quarter else 'YR'
        timeline[str(g.course_number).strip()].append(
            (term_key(g.school_year, quarter), g.letter_grade.strip().upper()))
    for number in timeline:
        timeline[number].sort(key=lambda pair: pair[0])
    return dict(timeline)


def check_prerequisites(entries, timeline, courses_by_number):
    """Evaluate each scheduled course's prerequisite rule.

    ``timeline`` — from build_completion_timeline (prior + same-year grades).
    ``courses_by_number`` — {course_number: Course} for prerequisite rules.
    """
    # What the student is merely SCHEDULED for, and when — used to distinguish
    # "prerequisite not met" from "prerequisite running earlier this year".
    scheduled = defaultdict(list)
    for e in entries:
        scheduled[str(e.course_number).strip()].append(term_key(e.school_year, e.term))

    findings = []
    for entry in entries:
        if entry.is_non_class or entry.is_advisory:
            continue
        course = courses_by_number.get(str(entry.course_number).strip())
        rule = rules_from_json(getattr(course, 'prereq_rules_json', None)) if course else None
        if not rule or (not rule['clauses'] and not rule['needs_review']):
            continue

        starts = term_key(entry.school_year, entry.term)

        if rule['needs_review'] and not rule['clauses']:
            findings.append(_finding(entry, rule, 'review', rule['text']))
            continue

        for clause in rule['clauses']:
            status, detail = _evaluate_clause(clause, starts, timeline, scheduled)
            if status == 'ok':
                continue
            if rule['advisory'] and status in ('missing', 'low_grade'):
                status = 'advisory'
            findings.append(_finding(entry, rule, status, detail, clause))

        if rule['needs_review']:
            findings.append(_finding(entry, rule, 'review', rule['text']))

    return findings


def _evaluate_clause(clause, starts, timeline, scheduled):
    numbers = clause.get('any_of') or []
    min_grade = clause.get('min_grade') or 'D-'
    required_all = clause.get('all_required')

    satisfied, low, in_progress = [], [], []
    for number in numbers:
        attempts = timeline.get(number, [])
        earlier = [(k, g) for k, g in attempts if k < starts]
        if any(grade_at_least(g, min_grade) for _, g in earlier):
            satisfied.append(number)
        elif earlier:
            low.append((number, max(g for _, g in earlier)))
        elif clause.get('concurrent_ok') and any(
                k <= starts for k in scheduled.get(number, [])):
            in_progress.append(number)
        elif any(k < starts for k in scheduled.get(number, [])):
            # Scheduled earlier this year but not graded yet — the 4x4 case.
            in_progress.append(number)

    if required_all:
        if len(satisfied) == len(numbers):
            return 'ok', ''
    elif satisfied:
        return 'ok', ''

    if in_progress:
        return 'in_progress', clause.get('label', '')
    if low:
        number, grade = low[0]
        return 'low_grade', f"{clause.get('label', '')} (earned {grade}, needs {min_grade})"
    return 'missing', clause.get('label', '')


def _finding(entry, rule, status, detail, clause=None):
    return {
        'course_number': entry.course_number,
        'course_title': entry.course_title,
        'period': entry.period,
        'term': entry.term,
        'status': status,
        'detail': detail,
        'requirement': rule['text'],
        'min_grade': (clause or {}).get('min_grade'),
    }


SEVERITY = {'missing': 0, 'low_grade': 1, 'in_progress': 2,
            'review': 3, 'advisory': 4}


def analyze_student_schedule(entries, grade_records, courses_by_number,
                             expected_classes=DEFAULT_EXPECTED_CLASSES):
    """Full analysis for one student-year."""
    completeness = analyze_completeness(entries, expected_classes)
    timeline = build_completion_timeline(grade_records)
    findings = check_prerequisites(entries, timeline, courses_by_number)

    # A semester course occupies two rows ([S1] in one quarter, [S2] in the
    # next), so an unmet prerequisite would otherwise be reported twice for
    # what the counselor thinks of as one class. Collapse to one finding per
    # course+requirement, keeping the earliest term it applies from.
    deduped = {}
    for f in findings:
        key = (f['course_title'], f['requirement'], f['status'], f['detail'])
        current = deduped.get(key)
        if current is None or term_key('', f['term']) < term_key('', current['term']):
            deduped[key] = f
    findings = list(deduped.values())
    findings.sort(key=lambda f: (SEVERITY.get(f['status'], 9), f['period'] or 0))

    blocking = [f for f in findings if f['status'] in ('missing', 'low_grade')]
    return {
        'completeness': completeness,
        'findings': findings,
        'blocking_count': len(blocking),
        'has_issues': bool(blocking) or not completeness['is_complete'],
    }
