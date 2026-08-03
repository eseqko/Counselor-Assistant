"""Where a cohort sits in the master schedule.

Answers "are my Newcomers stacked in one teacher's section, or one period?" —
the question you take to a master-schedule conversation.

The number that matters is not the raw count. A period holding 8 Newcomers
means nothing until you know whether that's 8 out of 10 or 8 out of 200. So
every slice carries a CONCENTRATION INDEX: the cohort's share of that slice
divided by its share of the whole caseload. 1.0 is exactly proportional; 2.0
means twice the representation you'd expect if scheduling were blind to it.

Pure functions — no request context, no ORM queries — so the arithmetic is
testable without seeding a database.
"""
from collections import defaultdict

# A slice this small is noise: one extra student swings the index wildly, and
# naming a teacher on the strength of two students invites a bad conversation.
MIN_SLICE_FOR_FLAG = 5
# Index at or above this is worth a second look.
OVER_REPRESENTED = 1.5
UNDER_REPRESENTED = 0.5


def schedule_key(entry, dimension):
    """The slice an entry belongs to, or None if it can't be placed."""
    if dimension == 'period':
        return f'Period {entry.period}' if entry.period is not None else None
    if dimension == 'teacher':
        return entry.teacher_name or None
    if dimension == 'course':
        return entry.course_title or None
    if dimension == 'advisory':
        return entry.section_id or entry.teacher_name or None
    return None


def build_concentration(students, entries, cohort_of, dimension,
                        term='all', include_advisory_only=False):
    """Cross-tabulate a caseload's schedule slices against cohort membership.

    ``students``   — the caseload (used for the baseline shares).
    ``entries``    — ScheduleEntry rows for those students.
    ``cohort_of``  — {student_id: cohort label}.
    ``dimension``  — 'period' | 'teacher' | 'course' | 'advisory'.

    Returns {'cohorts', 'baseline', 'rows', 'total_students', 'flagged'}.
    """
    total_students = len(students)
    baseline_counts = defaultdict(int)
    for sid in cohort_of:
        baseline_counts[cohort_of[sid]] += 1
    baseline = {c: (n / total_students if total_students else 0)
                for c, n in baseline_counts.items()}

    # slice -> cohort -> {student ids}. Sets because a student appears once per
    # term per period; counting rows would multiply them by up to four.
    grid = defaultdict(lambda: defaultdict(set))
    for e in entries:
        if e.is_non_class:
            continue                       # a "Vice Principal" row is not a class
        if include_advisory_only and not e.is_advisory:
            continue
        if not include_advisory_only and dimension == 'advisory' and not e.is_advisory:
            continue
        if term and term != 'all' and e.term != term:
            continue
        key = schedule_key(e, dimension)
        if key is None:
            continue
        cohort = cohort_of.get(e.student_id)
        if cohort is None:
            continue                       # not on this caseload
        grid[key][cohort].add(e.student_id)

    cohorts = sorted(baseline_counts, key=lambda c: (-baseline_counts[c], c))

    rows = []
    for slice_label, by_cohort in grid.items():
        slice_students = set()
        for ids in by_cohort.values():
            slice_students |= ids
        slice_total = len(slice_students)

        cells = []
        for cohort in cohorts:
            count = len(by_cohort.get(cohort, ()))
            share = count / slice_total if slice_total else 0
            base = baseline.get(cohort, 0)
            index = (share / base) if base else 0
            flagged = (slice_total >= MIN_SLICE_FOR_FLAG
                       and count > 0 and index >= OVER_REPRESENTED)
            cells.append({
                'cohort': cohort, 'count': count, 'share': share,
                'index': index, 'flagged': flagged,
                'small_sample': slice_total < MIN_SLICE_FOR_FLAG,
            })
        rows.append({
            'label': slice_label,
            'total': slice_total,
            'cells': cells,
        })

    rows.sort(key=_row_sort_key)
    flagged = [
        {'slice': r['label'], 'cohort': c['cohort'], 'count': c['count'],
         'total': r['total'], 'share': c['share'], 'index': c['index']}
        for r in rows for c in r['cells'] if c['flagged']
    ]
    flagged.sort(key=lambda f: -f['index'])

    return {
        'cohorts': cohorts,
        'baseline': baseline,
        'baseline_counts': dict(baseline_counts),
        'rows': rows,
        'total_students': total_students,
        'flagged': flagged,
    }


def _row_sort_key(row):
    """Periods numerically ("Period 10" after "Period 2"), everything else A-Z."""
    label = row['label']
    if label.startswith('Period '):
        tail = label.split(' ', 1)[1]
        if tail.isdigit():
            return (0, int(tail), '')
    return (1, 0, label.lower())


def chart_payload(result):
    """Stacked-bar data: one bar per slice, one segment per cohort."""
    return {
        'labels': [r['label'] for r in result['rows']],
        'series': [
            {
                'name': cohort,
                'data': [next((c['count'] for c in r['cells']
                               if c['cohort'] == cohort), 0)
                         for r in result['rows']],
            }
            for cohort in result['cohorts']
        ],
    }
