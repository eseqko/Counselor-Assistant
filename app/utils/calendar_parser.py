"""Parse a Jefferson Union HSD school-calendar PDF into calendar data.

Best-effort, district-specific. The decisive fields — school year, first/last
day, and each quarter's start/end — are extracted from stable anchors ("Qtr
One 1st Report:", etc). Semesters are DERIVED from quarters (Fall = Q1 start
→ Q2 end, Spring = Q3 start → Q4 end), which is exactly how this district's
semesters line up, so no fragile semester-row parsing is needed. Grades-due
dates are a best-effort bonus.

The result is meant to PRE-FILL the calendar form for human review, not to be
saved blindly — `warnings` lists anything that couldn't be parsed.
"""
import re
from datetime import date

_MONTHS = {
    'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3,
    'apr': 4, 'april': 4, 'may': 5, 'jun': 6, 'june': 6, 'jul': 7, 'july': 7,
    'aug': 8, 'august': 8, 'sep': 9, 'sept': 9, 'september': 9,
    'oct': 10, 'october': 10, 'nov': 11, 'november': 11, 'dec': 12, 'december': 12,
}

_ORDINALS = {'One': 1, 'Two': 2, 'Three': 3, 'Four': 4}

# A "Month Day" token, e.g. "Sept 3", "March 15", "Oct14".
_MD = r'([A-Za-z]+)\.?\s*(\d{1,2})'

# Anchors that mark the end of a quarter row's trailing data (used to bound
# the window we scan for a final-due date).
_ANCHORS = ('Qtr ', 'FALL SEMESTER', 'SPRING SEMESTER', 'FOR SCHOOLS',
            'TERM ONE', 'TERM TWO', '1st Report:', '2nd Report:',
            '3rd Report:', 'Grades Due', 'LEGEND')


def _month_num(word):
    return _MONTHS.get(word.strip().lower().rstrip('.'))


def _md_to_date(month_word, day, year_first, year_second):
    """Resolve a Month+Day to a date, inferring the year from the school year.

    Months Aug-Dec belong to the first calendar year; Jan-Jul to the second.
    """
    m = _month_num(month_word)
    if not m:
        return None
    try:
        day = int(day)
    except (ValueError, TypeError):
        return None
    year = year_first if m >= 8 else year_second
    try:
        return date(year, m, day)
    except ValueError:
        return None


def _last_md_in(window, y1, y2):
    """Return the last valid Month-Day date found in a text window, or None."""
    found = None
    for mt in re.finditer(_MD, window):
        d = _md_to_date(mt.group(1), mt.group(2), y1, y2)
        if d:
            found = d
    return found


def _window_after(text, pos):
    """Substring from pos until the next structural anchor."""
    end = len(text)
    for a in _ANCHORS:
        i = text.find(a, pos)
        if i != -1:
            end = min(end, i)
    return text[pos:end]


def parse_calendar_pdf(filepath):
    """Extract calendar data from a JUHSD calendar PDF. Returns a dict.

    Keys: school_year, first_day, last_day, quarters, semesters, warnings.
    Raises ValueError only for unreadable / wrong-format files.
    """
    from PyPDF2 import PdfReader

    reader = PdfReader(filepath)
    if getattr(reader, 'is_encrypted', False):
        try:
            reader.decrypt('')
        except Exception:
            raise ValueError('This PDF is password-protected. Re-save it without a password.')

    text = ''
    for page in reader.pages:
        try:
            text += (page.extract_text() or '') + '\n'
        except Exception:
            continue

    if not text.strip():
        raise ValueError('Could not read any text from this PDF.')

    return parse_calendar_text(text)


def parse_calendar_text(text):
    """The pure-text half of the parser (unit-testable without a PDF)."""
    warnings = []

    # --- school year ---
    sy_m = re.search(r'(\d{4})\s*-\s*(\d{4})\s*SCHOOL CALENDAR', text)
    if not sy_m:
        raise ValueError("Couldn't find a 'YYYY-YYYY SCHOOL CALENDAR' heading — "
                         "this may not be a recognized district calendar.")
    y1, y2 = int(sy_m.group(1)), int(sy_m.group(2))
    school_year = f'{y1}-{y2}'

    # --- first / last day ---
    def _full_date(label):
        m = re.search(label + r'\s*-\s*([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})', text)
        if not m:
            return None
        mn = _month_num(m.group(1))
        if not mn:
            return None
        try:
            return date(int(m.group(3)), mn, int(m.group(2)))
        except ValueError:
            return None

    first_day = _full_date('First Day of School')
    last_day = _full_date('Last Day of School')
    if not first_day:
        warnings.append('first day of school')
    if not last_day:
        warnings.append('last day of school')

    # --- quarters ---
    quarters = []
    for word, n in _ORDINALS.items():
        m1 = re.search(rf'Qtr {word} 1st Report:\s*{_MD}\s*-\s*{_MD}', text)
        m2 = re.search(rf'Qtr {word} 2nd Report:\s*{_MD}\s*-\s*{_MD}', text)
        start = _md_to_date(m1.group(1), m1.group(2), y1, y2) if m1 else None
        end = _md_to_date(m2.group(3), m2.group(4), y1, y2) if m2 else None

        # progress-report due: "Q{n} <Month Day>" (absent on older sheets)
        progress_due = None
        pm = re.search(rf'Q{n}\s+{_MD}', text)
        if pm:
            progress_due = _md_to_date(pm.group(1), pm.group(2), y1, y2)

        # final due: last date token in the window trailing the 2nd-report range
        final_due = None
        if m2:
            final_due = _last_md_in(_window_after(text, m2.end()), y1, y2)

        if not start or not end:
            warnings.append(f'Q{n} dates')
        quarters.append({
            'n': n, 'start': start, 'end': end,
            'progress_due': progress_due, 'final_due': final_due,
        })

    quarters.sort(key=lambda q: q['n'])

    # --- semesters: derived from quarters (Fall = Q1→Q2, Spring = Q3→Q4) ---
    semesters = _derive_semesters(quarters)

    return {
        'school_year': school_year,
        'first_day': first_day,
        'last_day': last_day,
        'quarters': quarters,
        'semesters': semesters,
        'warnings': warnings,
    }


def _derive_semesters(quarters):
    by_n = {q['n']: q for q in quarters}
    out = []
    pairs = [(1, 1, 2), (2, 3, 4)]  # (semester_n, first_q, second_q)
    for sem_n, qa, qb in pairs:
        a, b = by_n.get(qa), by_n.get(qb)
        if not a or not b:
            continue
        out.append({
            'n': sem_n,
            'start': a.get('start'),
            'end': b.get('end'),
            'final_due': b.get('final_due'),
        })
    return out
