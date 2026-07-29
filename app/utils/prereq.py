"""Turn catalog prerequisite prose into rules a schedule can be checked against.

The district catalog states prerequisites the way a human would write them —
"Pass MC2 with C- or better", "Passing grade in Biology", '"B" or above in
World History preferred'. This module parses that into structured clauses and,
critically, refuses to guess: anything it cannot resolve to a real course is
marked ``needs_review`` so it surfaces as "check this by hand" rather than
silently passing a student who hasn't met a requirement, or failing one who has.

Shape of a parsed rule:

    {
      'text': '<original prose>',
      'advisory': bool,        # "recommended"/"preferred" — not a hard gate
      'needs_review': bool,    # couldn't be resolved; a human must look
      'clauses': [             # ALL clauses must hold
         {'any_of': ['22002', '22003'],   # ANY of these course numbers
          'min_grade': 'C-',
          'concurrent_ok': False,
          'label': 'MC2'}
      ]
    }
"""
import json
import re

from app.models.grade import GPA_POINTS

# Lowest grade that counts as passing when the catalog just says "passing grade"
# or names a course with no threshold. Matches GradeRecord.is_passing, which
# treats anything above F/NP/I/W as a pass.
DEFAULT_MIN_GRADE = 'D-'

_ADVISORY_RE = re.compile(r'\b(recommend|preferred|prefer)\w*', re.I)
_CONCURRENT_RE = re.compile(r'\bconcurrent(ly)?\b|\benrollment in\b', re.I)

# Grade thresholds. Every pattern demands the letter be a STANDALONE token —
# (?<![A-Za-z])X(?![A-Za-z]) — because a loose [A-D] match eats the leading C of
# "Course", "Concert" and "Chemistry", which silently turned "Passing grade in
# Concert Band" into a C-or-better requirement on a course named "oncert Band".
_GRADE_PATTERNS = [
    # C- or better / C or higher / "B" or above
    re.compile(r'"?(?<![A-Za-z])([A-D][+-]?)(?![A-Za-z])"?\s*'
               r'or\s+(?:better|higher|above)', re.I),
    # with a C / with C-
    re.compile(r'\bwith\s+(?:a\s+)?"?(?<![A-Za-z])([A-D][+-]?)(?![A-Za-z])"?', re.I),
    # C- in Spanish 3   (grade leads the phrase)
    re.compile(r'^\s*"?(?<![A-Za-z])([A-D][+-]?)(?![A-Za-z])"?\s+in\b', re.I),
]

# Phrases that carry no course reference at all — eligibility conditions a
# transcript cannot answer. Listed so they're classified deliberately rather
# than falling through the course matcher and matching something by accident.
_NON_COURSE_TERMS = (
    'application', 'election', 'teacher approval', 'counselor approval',
    'elpac', 'ell status', 'el 9-10', 'iep', 'audition', 'interview',
    'prerequisite art class',      # deliberately vague in the catalog
)

# Leading verbs/qualifiers to strip before matching a course name.
_STRIP_PREFIXES = re.compile(
    r'^(?:pass(?:ing)?(?:\s+grade)?(?:\s+in)?|completion\s+of|'
    r'enrollment\s+in|at\s+least\s+one\s+semester\s+of|at\s+least)\s+', re.I)
_STRIP_SUFFIXES = re.compile(
    r'\s*(?:both\s+semesters|one\s+semester|\(.*?\)|preferred|recommended)\s*$',
    re.I)


def grade_at_least(earned, minimum):
    """Is ``earned`` at least as good as ``minimum`` on the 4.0 scale?"""
    if not earned or not minimum:
        return False
    e = GPA_POINTS.get(earned.strip().upper())
    m = GPA_POINTS.get(minimum.strip().upper())
    if e is None or m is None:
        return False
    return e >= m


class CourseIndex:
    """Resolve a course name or abbreviation to catalog course numbers."""

    # Abbreviations the catalog uses in prerequisite text but not in titles.
    # Keys are stored NORMALIZED (lowercase, punctuation -> spaces), because
    # lookup happens after normalization: "Trig/Precalculus" arrives as
    # "trig precalculus".
    ALIASES = {
        'mc1': 'math course 1', 'mc2': 'math course 2', 'mc3': 'math course 3',
        'trig precalculus': 'trigonometry precalculus',
        'precalculus': 'trigonometry precalculus',
        'foods nutrition': 'foods nutrition',
    }

    def __init__(self, courses):
        """``courses`` — iterable of (course_number, title)."""
        self.by_norm = {}
        for number, title in courses:
            if not number or not title:
                continue
            self.by_norm.setdefault(self._norm(title), []).append(str(number))

    @staticmethod
    def _norm(text):
        text = (text or '').lower()
        text = re.sub(r'\[s[12]\]', ' ', text)          # drop [S1]/[S2] markers
        # 'CP' is a level marker prereq prose usually omits, so it's dropped.
        # 'AP'/'Honors' are NOT — they name genuinely different courses.
        text = re.sub(r'\b(cp)\b', ' ', text)
        text = re.sub(r'[^a-z0-9 ]', ' ', text)
        return re.sub(r'\s+', ' ', text).strip()

    def resolve(self, phrase):
        """Course numbers matching ``phrase``. [] when absent OR ambiguous.

        Ambiguity returns nothing on purpose. Silently checking the wrong
        course is worse than admitting we don't know — "World History" matching
        AP World History would fail every student who took the CP version.
        """
        key = self._norm(phrase)
        norm = self._norm(self.ALIASES.get(key, key))
        if not norm:
            return []
        if norm in self.by_norm:
            return list(dict.fromkeys(self.by_norm[norm]))
        starts = [nums for key, nums in self.by_norm.items() if key.startswith(norm)]
        if len(starts) == 1:
            return list(dict.fromkeys(starts[0]))
        if len(starts) > 1:
            return []                       # ambiguous prefix
        contains = [nums for key, nums in self.by_norm.items() if norm in key]
        if len(contains) == 1:
            return list(dict.fromkeys(contains[0]))
        return []


def parse_prerequisite(text, index):
    """Parse one catalog prerequisite string into a rule dict."""
    raw = (text or '').strip()
    rule = {'text': raw, 'advisory': False, 'needs_review': False, 'clauses': []}
    if not raw or raw.lower() in ('none', 'n/a', '-'):
        return rule

    rule['advisory'] = bool(_ADVISORY_RE.search(raw))

    # ';' separates independent requirements that must ALL hold.
    for part in re.split(r'\s*;\s*', raw):
        clause = _parse_clause(part, index)
        if clause is None:
            # A part naming no checkable course makes the whole rule advisory
            # for a human rather than silently dropping a requirement.
            if not _is_non_course(part):
                rule['needs_review'] = True
            elif not rule['clauses']:
                rule['needs_review'] = True
            continue
        rule['clauses'].append(clause)

    if not rule['clauses']:
        rule['needs_review'] = True
    return rule


def _is_non_course(text):
    low = (text or '').lower()
    return any(term in low for term in _NON_COURSE_TERMS)


def _extract_min_grade(part):
    """Grade threshold stated in ``part``, or the default passing mark."""
    for pattern in _GRADE_PATTERNS:
        m = pattern.search(part)
        if m:
            return m.group(1).upper()
    return DEFAULT_MIN_GRADE


def _strip_grade_phrases(part):
    """Remove the grade wording so it can't be read as part of a course name."""
    out = part
    for pattern in _GRADE_PATTERNS:
        out = pattern.sub(' ', out)
    # A trailing "with ..." qualifier is about the grade, not the course name.
    out = re.sub(r'\bwith\s+(?:a\s+)?$', ' ', out, flags=re.I)
    return out


def _parse_clause(part, index):
    """One ';'-separated requirement -> a clause dict, or None if unresolvable."""
    part = part.strip()
    if not part or _is_non_course(part):
        return None

    concurrent = bool(_CONCURRENT_RE.search(part))
    min_grade = _extract_min_grade(part)

    body = _strip_grade_phrases(part)
    # "concurrent" is captured as a flag above; leaving the word in the body
    # stops "concurrent MC3" from resolving to MC3.
    body = _CONCURRENT_RE.sub(' ', body)
    # Strip repeatedly: "Pass at least one semester of Math Course 1" needs two
    # passes, and grade removal leaves a dangling "in"/"of" ("C or better in
    # Art 1 CP" -> " in Art 1 CP").
    for _ in range(4):
        stripped = _STRIP_PREFIXES.sub('', body.strip())
        stripped = re.sub(r'^(?:in|of|a)\s+', '', stripped, flags=re.I)
        if stripped == body.strip():
            break
        body = stripped
    body = _STRIP_SUFFIXES.sub('', body).strip(' ,.&')
    # Removing "C- or better" then "both semesters" can leave a dangling
    # connective ("Trig/Precalculus with"), which resolves to nothing.
    body = re.sub(r'\s+(?:with|in|of|and|or|a)\s*$', '', body, flags=re.I)
    body = re.sub(r'\s+', ' ', body)
    if not body:
        return None

    def clause(numbers, all_required=False):
        return {'any_of': list(dict.fromkeys(numbers)), 'min_grade': min_grade,
                'concurrent_ok': concurrent, 'label': body,
                'all_required': all_required}

    # Try the WHOLE phrase first. Splitting eagerly breaks real course names
    # that contain the separators — "Foods & Nutrition" is one course, not two.
    whole = index.resolve(body)
    if whole:
        return clause(whole)

    # " or " / "," -> any one of these satisfies the requirement.
    alternatives = [a.strip() for a in re.split(r'\s+or\s+|,', body) if a.strip()]
    if len(alternatives) > 1:
        numbers = []
        for alt in alternatives:
            got = index.resolve(alt)
            if not got:
                numbers = []
                break
            numbers.extend(got)
        if numbers:
            return clause(numbers)

    # " and " / "&" -> every named course is required.
    conjuncts = [c.strip() for c in re.split(r'\s+and\s+|&', body) if c.strip()]
    if len(conjuncts) > 1:
        numbers = []
        for name in conjuncts:
            got = index.resolve(name)
            if not got:
                return None
            numbers.extend(got)
        return clause(numbers, all_required=True)

    return None


def rules_to_json(rule):
    return json.dumps(rule)


def rules_from_json(raw):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None
