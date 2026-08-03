"""D/F outcomes for a counselor's own students, grouped by section.

Answers "which sections are my students struggling in?" by joining the schedule
(who sits where, and with whom) to the grades already imported.

Scope matters and is deliberate: this counts ONLY the caseload of the counselor
viewing it. A teacher's overall pass rate is not what's being measured and this
cannot produce it — a counselor typically holds a handful of students in any
one section. Read as "my students in this section are struggling", which is a
support-targeting signal, not as a measure of the teacher.

Two guards against drawing conclusions the data won't support:
  * sections with fewer than MIN_SECTION_STUDENTS of your students report their
    counts but are never RANKED or flagged;
  * ungraded marks are excluded from both numerator and denominator rather than
    counted as passing or failing.
"""
from collections import defaultdict

# Below this many of your students in a section, a rate is noise: with three
# students one D is 33%, and that number invites a conversation the data can't
# support.
MIN_SECTION_STUDENTS = 5

# Letters that count as a struggling outcome. D is included on purpose — it
# earns credit but does not satisfy a-g, so it is the signal a counselor acts on.
FAILING_GRADES = {'D+', 'D', 'D-', 'F', 'NP'}

# Marks that carry no pass/fail signal. Excluded from the denominator entirely
# rather than counted either way — 'NM' means the teacher hasn't graded yet, and
# treating that as a failure is the bug that once printed "NOT PASSING" to
# parents for an ungraded course.
NO_SIGNAL_GRADES = {'NM', 'I', 'W', '', None}

# Quarter ordering for "most recent graded term wins".
_QUARTER_RANK = {1: 1, 2: 2, 3: 3, 4: 4, None: 0}


def is_failing(letter):
    return (letter or '').strip().upper() in FAILING_GRADES


def has_signal(letter):
    value = (letter or '').strip().upper()
    return bool(value) and value not in NO_SIGNAL_GRADES


def latest_grade_per_course(grade_records):
    """(student_id, course_number) -> the grade that represents where they stand.

    A course produces a grade every quarter, so a student who pulled a D up to a
    C would otherwise be counted as both. Keep the most recent GRADED term, and
    prefer a final grade over a progress report within the same term.
    """
    best = {}
    for g in grade_records:
        if not g.course_number or not has_signal(g.letter_grade):
            continue
        key = (g.student_id, str(g.course_number).strip())
        rank = (g.school_year or '', _QUARTER_RANK.get(g.quarter, 0),
                1 if (g.grade_type or '') == 'final' else 0)
        current = best.get(key)
        if current is None or rank > current[0]:
            best[key] = (rank, g.letter_grade.strip().upper())
    return {key: value[1] for key, value in best.items()}


def build_section_outcomes(entries, grade_records, dimension='teacher',
                           cohort_of=None, cohort_filter=None):
    """D/F rates per section for the caseload.

    ``entries``       — ScheduleEntry rows (who is in which section).
    ``grade_records`` — GradeRecord rows for those students.
    ``dimension``     — 'teacher' | 'period' | 'course'.
    ``cohort_of``     — optional {student_id: label} to narrow the population.
    ``cohort_filter`` — when set with cohort_of, only that cohort is counted.
    """
    grades = latest_grade_per_course(grade_records)

    # (student, course) -> the section it belongs to. The schedule is
    # authoritative for who taught what; GradeRecord.teacher is a fallback for
    # installs that import grades but not schedules.
    section_of = {}
    for e in entries:
        if e.is_non_class or e.is_advisory or not e.course_number:
            continue
        key = (e.student_id, str(e.course_number).strip())
        label = _dimension_label(e, dimension)
        if label:
            section_of[key] = label

    buckets = defaultdict(lambda: {'students': set(), 'failing': set(),
                                   'grades': []})
    for (student_id, course_number), letter in grades.items():
        if cohort_of is not None and cohort_filter:
            if cohort_of.get(student_id) != cohort_filter:
                continue
        label = section_of.get((student_id, course_number))
        if label is None:
            continue
        bucket = buckets[label]
        bucket['students'].add(student_id)
        bucket['grades'].append(letter)
        if is_failing(letter):
            bucket['failing'].add(student_id)

    rows = []
    for label, bucket in buckets.items():
        total = len(bucket['students'])
        failing = len(bucket['failing'])
        rows.append({
            'label': label,
            'students': total,
            'failing': failing,
            'rate': (failing / total) if total else 0,
            'small_sample': total < MIN_SECTION_STUDENTS,
        })

    # Rankable rows first, worst rate first; small samples always last so they
    # can't top a list on the strength of two students.
    rows.sort(key=lambda r: (r['small_sample'], -r['rate'], -r['students']))

    counted = [r for r in rows if not r['small_sample']]
    overall_students = sum(r['students'] for r in rows)
    overall_failing = sum(r['failing'] for r in rows)

    return {
        'rows': rows,
        'rankable': counted,
        'overall_rate': (overall_failing / overall_students) if overall_students else 0,
        'overall_students': overall_students,
        'overall_failing': overall_failing,
        'suppressed': len(rows) - len(counted),
    }


def _dimension_label(entry, dimension):
    if dimension == 'teacher':
        return entry.teacher_name or None
    if dimension == 'period':
        return f'Period {entry.period}' if entry.period is not None else None
    if dimension == 'course':
        return entry.course_title or None
    return None


def chart_payload(result, limit=12):
    """Bar data for the rankable sections, worst first."""
    rows = result['rankable'][:limit]
    return {
        'labels': [r['label'] for r in rows],
        'rates': [round(r['rate'] * 100, 1) for r in rows],
        'students': [r['students'] for r in rows],
    }


def student_course_outcomes(entries, grade_records):
    """One student's current courses with the grade that represents where they
    stand, and whether it's a D/F.

    The per-student counterpart of the section report: instead of "which
    sections are my students struggling in", this answers "which of THIS
    student's classes are they earning a D or F in, and who teaches them".

    ``entries``       — the student's ScheduleEntry rows for one year.
    ``grade_records`` — that student's GradeRecord rows (any span).

    Returns {'courses': [...], 'failing_count': int}. Ordered worst-first so a
    struggling course leads. Non-class/advisory rows and courses with no signal
    yet (ungraded) are omitted from the failing count but still listed, so the
    counselor sees the full picture with the concern surfaced.
    """
    grades = latest_grade_per_course(grade_records)

    seen = set()
    courses = []
    for e in entries:
        if e.is_non_class or e.is_advisory or not e.course_number:
            continue
        number = str(e.course_number).strip()
        if number in seen:
            continue                       # collapse the [S1]/[S2] pair
        seen.add(number)
        letter = grades.get((e.student_id, number))
        courses.append({
            'course_number': number,
            'course_title': e.course_title,
            'teacher': e.teacher_name or '',
            'period': e.period,
            'letter': letter,
            'graded': has_signal(letter),
            'failing': is_failing(letter),
        })

    # Failing first, then ungraded, then passing; period order within each.
    def _rank(c):
        tier = 0 if c['failing'] else (1 if not c['graded'] else 2)
        return (tier, c['period'] if c['period'] is not None else 99)
    courses.sort(key=_rank)

    return {
        'courses': courses,
        'failing_count': sum(1 for c in courses if c['failing']),
    }
