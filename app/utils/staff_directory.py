"""Build the staff directory out of an imported class schedule.

The directory used to fill up only from GRADE imports, which means it stayed
empty until the first grades of the year landed — precisely the weeks a
counselor most needs to know who teaches what. A schedule import knows every
teacher on day one, and knows more about them than a grade row does: the room
they teach in, the courses (hence the department), and, for administrators,
their actual job title.

Two rules run through all of this:

* **Never overwrite the counselor.** These are derived guesses filling in for
  absent data. A field a human has typed is left exactly as it is.
* **Don't guess when the data is ambiguous.** A teacher who appears in two rooms
  equally often gets no room rather than a coin-flip that sends someone to the
  wrong door.
"""
from collections import Counter, defaultdict

# Synergy carries an administrator's job title in the course_title of a
# non-class row ("Vice Principal" sitting in period 7 with no room). That row is
# the only place the SIS states what the person actually does, so it is worth
# reading rather than defaulting everyone to Teacher.
_ADMIN_TITLE_MAP = (
    ('assistant principal', 'Administrator'),
    ('vice principal', 'Administrator'),
    ('principal', 'Administrator'),
    ('administrator', 'Administrator'),
    ('dean', 'Administrator'),
    ('counselor', 'Counselor'),
)

# Fields this module is willing to derive. Order is display order.
DERIVED_FIELDS = ('title', 'room', 'department')


def _norm(name):
    """Case-insensitive identity for a staff name, matching the grade importer."""
    return (name or '').strip().lower()


def _role_from_title(course_title):
    """Staff.TITLES value implied by an administrative course title, or None."""
    t = (course_title or '').strip().lower()
    if not t:
        return None
    for needle, role in _ADMIN_TITLE_MAP:
        if t == needle or t.startswith(needle):
            return role
    return None


def _clear_winner(values):
    """The single most common value, or None if absent or tied.

    A tie means the SIS genuinely shows the person in two places; inventing a
    winner would be worse than leaving the field for the counselor to fill.
    """
    counts = Counter(v for v in values if v)
    if not counts:
        return None
    ranked = counts.most_common()
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return None
    return ranked[0][0]


def _get(row, field):
    """Read a field from either a staged import dict or a ScheduleEntry."""
    if isinstance(row, dict):
        return row.get(field)
    return getattr(row, field, None)


def derive_staff_from_schedule(rows, department_by_course=None):
    """Collapse schedule rows into one derived record per staff member.

    ``rows`` — staged import dicts or ScheduleEntry objects. ``department_by_course``
    maps course_number -> department name (from the Course catalog).

    Returns {normalized_name: {'name', 'title', 'room', 'department'}}, where a
    derived field is absent when the data did not support a confident answer.
    """
    dept_of = department_by_course or {}
    grouped = defaultdict(lambda: {'name': '', 'rooms': [], 'depts': [], 'roles': []})

    for row in rows:
        raw_name = (_get(row, 'teacher_name') or '').strip()
        if not raw_name:
            continue
        g = grouped[_norm(raw_name)]
        # Keep the first spelling seen, mirroring how grade imports store names.
        if not g['name']:
            g['name'] = raw_name

        if _get(row, 'is_non_class'):
            role = _role_from_title(_get(row, 'course_title'))
            if role:
                g['roles'].append(role)
            # An admin assignment row has no real room or department.
            continue

        room = (_get(row, 'room') or '').strip()
        if room:
            g['rooms'].append(room)
        dept = (dept_of.get(_get(row, 'course_number')) or '').strip()
        if dept:
            g['depts'].append(dept)

    derived = {}
    for key, g in grouped.items():
        rec = {'name': g['name']}
        # An administrative row states the job outright, so it wins over the
        # default. Someone can be a VP and still supervise a TA period.
        role = _clear_winner(g['roles'])
        rec['title'] = role or 'Teacher'
        room = _clear_winner(g['rooms'])
        if room:
            rec['room'] = room
        dept = _clear_winner(g['depts'])
        if dept:
            rec['department'] = dept
        derived[key] = rec
    return derived


def apply_staff_records(derived, existing, make_staff):
    """Create missing staff and backfill blank fields on the ones that exist.

    ``existing`` — {normalized_name: Staff}. ``make_staff`` — callable taking
    keyword fields and registering a new record (kept injectable so this stays
    unit-testable without a database).

    Returns (created_count, enriched_count). A record is "enriched" when at
    least one previously-blank derived field got a value; a field the counselor
    already filled is never touched, so re-importing is safe.
    """
    created = enriched = 0
    for key, rec in derived.items():
        staff = existing.get(key)
        if staff is None:
            make_staff(**rec)
            created += 1
            continue
        touched = False
        for field in DERIVED_FIELDS:
            value = rec.get(field)
            if not value:
                continue
            if not (getattr(staff, field, None) or '').strip():
                setattr(staff, field, value)
                touched = True
        if touched:
            enriched += 1
    return created, enriched


def summarize(derived, existing_names):
    """Preview copy: how many staff an import would add vs. already knows."""
    known = {_norm(n) for n in existing_names}
    new = sorted(r['name'] for k, r in derived.items() if k not in known)
    return {
        'total': len(derived),
        'new': new,
        'new_count': len(new),
        'known_count': len(derived) - len(new),
    }
