"""District school-year calendar: quarter and semester windows.

One row per school year (e.g. "2027-2028"). Powers grade-/quarter-aware
benchmarks: current_quarter() / current_semester() in app/utils/helpers.py
look up the row covering "today" instead of guessing from the month.

Calendars are district-wide (not per-counselor) — they describe the school's
reporting calendar, not a personal preference. Quarter and semester windows
are stored as JSON so the schema doesn't need a column per reporting period.
"""
import json
from datetime import datetime, timezone, date

from app import db


def _parse_iso(s):
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


class SchoolCalendar(db.Model):
    __tablename__ = 'school_calendars'

    id = db.Column(db.Integer, primary_key=True)
    school_year = db.Column(db.String(9), unique=True, nullable=False, index=True)  # "2027-2028"
    first_day = db.Column(db.Date)
    last_day = db.Column(db.Date)

    # JSON list of quarters: [{n, start, end, progress_due, final_due}, ...]
    # JSON list of semesters: [{n, start, end, final_due}, ...]
    # All inner dates are ISO strings ("2027-10-08") or null.
    quarters_json = db.Column(db.Text)
    semesters_json = db.Column(db.Text)

    source = db.Column(db.String(120), default='manual')  # 'manual', 'seed', 'pdf:<name>'
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    # ---- accessors -------------------------------------------------------

    def quarters(self):
        """Return quarter dicts with parsed date objects, sorted by n."""
        try:
            raw = json.loads(self.quarters_json) if self.quarters_json else []
        except (json.JSONDecodeError, TypeError):
            return []
        out = []
        for q in raw:
            out.append({
                'n': q.get('n'),
                'start': _parse_iso(q.get('start')),
                'end': _parse_iso(q.get('end')),
                'progress_due': _parse_iso(q.get('progress_due')),
                'final_due': _parse_iso(q.get('final_due')),
            })
        return sorted(out, key=lambda x: (x['n'] is None, x['n']))

    def semesters(self):
        """Return semester dicts with parsed date objects, sorted by n."""
        try:
            raw = json.loads(self.semesters_json) if self.semesters_json else []
        except (json.JSONDecodeError, TypeError):
            return []
        out = []
        for s in raw:
            out.append({
                'n': s.get('n'),
                'start': _parse_iso(s.get('start')),
                'end': _parse_iso(s.get('end')),
                'final_due': _parse_iso(s.get('final_due')),
            })
        return sorted(out, key=lambda x: (x['n'] is None, x['n']))

    def _which(self, periods, d):
        """Return the period number covering d, or the most recent one started.

        Non-strict: if d falls in a gap between two periods (e.g. the weekend
        between Q1 ending and Q2 starting), returns the period that just ended,
        since the student has completed that period's work. Before the first
        period → first; after the last → last.
        """
        dated = [p for p in periods if p['start']]
        if not dated:
            return None
        if d < dated[0]['start']:
            return dated[0]['n']
        current = dated[0]['n']
        for p in dated:
            if p['start'] <= d:
                current = p['n']
            else:
                break
        return current

    def quarter_for(self, d, strict=False):
        qs = self.quarters()
        if strict:
            for q in qs:
                if q['start'] and q['end'] and q['start'] <= d <= q['end']:
                    return q['n']
            return None
        return self._which(qs, d)

    def semester_for(self, d, strict=False):
        ss = self.semesters()
        if strict:
            for s in ss:
                if s['start'] and s['end'] and s['start'] <= d <= s['end']:
                    return s['n']
            return None
        return self._which(ss, d)

    def quarter(self, n):
        for q in self.quarters():
            if q['n'] == n:
                return q
        return None

    # ---- mutators --------------------------------------------------------

    def set_quarters(self, quarters):
        """quarters: list of dicts with date objects or ISO strings."""
        self.quarters_json = json.dumps([_period_to_json(q, ('progress_due', 'final_due'))
                                         for q in quarters])

    def set_semesters(self, semesters):
        self.semesters_json = json.dumps([_period_to_json(s, ('final_due',))
                                          for s in semesters])

    @staticmethod
    def for_year(school_year):
        return SchoolCalendar.query.filter_by(school_year=school_year).first()


def _iso(v):
    if v is None:
        return None
    if isinstance(v, date):
        return v.isoformat()
    return str(v)


def _period_to_json(p, due_fields):
    out = {'n': p.get('n'), 'start': _iso(p.get('start')), 'end': _iso(p.get('end'))}
    for f in due_fields:
        out[f] = _iso(p.get(f))
    return out
