"""Seed the Course catalog from the district catalog shipped with the app.

`app/static/course_catalog/index.html` already carries the full JUHSD course
list — 127 courses with codes, credits, a-g area, grade level and prerequisite
prose — but purely as display data for the Catalog Wiki. Nothing reads it.

Importing it gives the rest of the app three things it otherwise has to ask the
counselor for: credits per course number (so schedule imports stop prompting),
a-g designation, and prerequisites that can actually be checked.

Credit arithmetic worth stating: a code like ``20001/20002`` with credits ``10``
is one year-long course delivered as two half-courses, so EACH course number is
worth 5. A single code with credits ``5`` is worth 5. That matches the schedule
export, where every row is one course number.
"""
import os
import re

CATALOG_HTML = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'static', 'course_catalog', 'index.html')

_ENTRY_RE = re.compile(
    r"\{id:'[^']+',\s*dept:'([^']*)',\s*name:'((?:[^'\\]|\\.)*)',\s*"
    r"code:'([^']*)',\s*grade:'([^']*)',\s*credits:'([^']*)',\s*"
    r"ag:'([^']*)',\s*type:'([^']*)',\s*(?:collegeCredit:\w+,\s*)?"
    r"prereq:'((?:[^'\\]|\\.)*)'")

DEPT_LABELS = {
    'social-science': 'Social Science', 'english': 'English',
    'mathematics': 'Mathematics', 'science': 'Science',
    'lote': 'World Languages', 'vpa': 'Visual & Performing Arts',
    'cte': 'Career Technical Education', 'pe': 'Physical Education',
    'electives': 'Electives', 'special-ed': 'Special Education',
}


def read_catalog(path=None):
    """Parse the shipped catalog into dicts. One entry per catalog ROW."""
    with open(path or CATALOG_HTML, encoding='utf-8') as fh:
        html = fh.read()

    out = []
    for dept, name, code, grade, credits, ag, ctype, prereq in _ENTRY_RE.findall(html):
        codes = [c.strip() for c in code.split('/') if c.strip()]
        if not codes:
            continue
        try:
            total_credits = float(credits)
        except ValueError:
            total_credits = None
        per_code = (total_credits / len(codes)) if total_credits else None
        out.append({
            'department': DEPT_LABELS.get(dept, dept.title()),
            'title': name.replace("\\'", "'"),
            'codes': codes,
            'grade_levels': grade,
            'credits_per_code': per_code,
            'ag_area': ag,
            'course_type': ctype,
            'prerequisites': prereq.replace("\\'", "'"),
        })
    return out


def seed_courses(db, Course, path=None, overwrite=False):
    """Create/refresh Course rows from the shipped catalog.

    Returns (created, updated, skipped). Existing rows are left alone unless
    ``overwrite`` — a counselor may have corrected a credit value by hand and
    that edit outranks the shipped file.
    """
    from app.utils.prereq import CourseIndex, parse_prerequisite, rules_to_json

    entries = read_catalog(path)

    # Index every course number -> title first, so prerequisite prose can be
    # resolved against the whole catalog rather than only what's already saved.
    pairs = [(code, e['title']) for e in entries for code in e['codes']]
    index = CourseIndex(pairs)

    existing = {c.course_number: c for c in Course.query.all() if c.course_number}
    created = updated = skipped = 0

    for entry in entries:
        rule = parse_prerequisite(entry['prerequisites'], index)
        rule_json = rules_to_json(rule) if entry['prerequisites'] else None

        for code in entry['codes']:
            course = existing.get(code)
            if course and not overwrite:
                # Backfill only what's genuinely missing; never clobber an edit.
                touched = False
                if course.credits is None and entry['credits_per_code'] is not None:
                    course.credits = entry['credits_per_code']
                    touched = True
                if not course.prerequisites and entry['prerequisites']:
                    course.prerequisites = entry['prerequisites']
                    course.prereq_rules_json = rule_json
                    touched = True
                updated += touched
                skipped += (not touched)
                continue

            if course is None:
                course = Course(course_number=code)
                db.session.add(course)
                existing[code] = course
                created += 1
            else:
                updated += 1

            course.title = entry['title']
            course.department_name = entry['department']
            course.credits = entry['credits_per_code']
            course.grade_levels = entry['grade_levels']
            course.subject_area = entry['department']
            course.course_type = entry['course_type']
            course.meets_requirement = entry['ag_area']
            course.prerequisites = entry['prerequisites']
            course.prereq_rules_json = rule_json
            course.is_active = True

    db.session.commit()
    return created, updated, skipped
