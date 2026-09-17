"""Senior / Post-Secondary 1:1 meetings.

One page to run a sit-down with a senior: live notes that autosave, the
post-secondary checklist for their pathway, the deadlines coming up for THEM
(school-wide dates plus their own applications, goals and follow-ups), and a
prompt bank of ASCA-aligned, Solution-Focused questions. Completing a meeting
logs it as a Note, so it shows in the student's timeline, the reminders digest
and the alert engine like any other contact.

Ownership: every read goes through owned_or_404 / caseload_student_or_404
(404, never 403). The per-counselor Sample Student may open a meeting so the
tool can be tried, but never appears on the roster.
"""
import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, jsonify, abort)
from flask_login import login_required, current_user

from app import db, csrf
from app.models.calendar_event import CalendarEvent
from app.models.college_career import CollegeCareerPlan, CollegeApplication
from app.models.goal import Goal
from app.models.note import Note
from app.models.senior_meeting import (SeniorMeeting, SeniorChecklistItem,
                                       PostSecondaryDeadline)
from app.models.student import Student
from app.utils import senior_meeting_content as content
from app.utils.audit import log_action
from app.utils.helpers import parse_date
from app.utils.roles import (owned_or_404, caseload_student_or_404,
                             admin_or_sole_user_required)

senior_meetings_bp = Blueprint('senior_meetings', __name__)

# Prompts whose 0-10 answer is also the meeting's headline scaling number.
SCALE_COLUMNS = {
    'scale_plan_progress': 'scale_plan',
    'fu_scale_again': 'scale_plan',
    'scale_stress': 'scale_stress',
    'next_confidence': 'scale_confidence',
}
NOTE_TYPES = [
    ('college_career', 'College/Career Planning'),
    ('financial_aid', 'Financial Aid'),
    ('student_conference', 'Student Conference'),
    ('four_year_plan', 'Four-Year Plan/Graduation'),
]
DEADLINE_HORIZON_DAYS = 300   # the rest of a senior's year, not just the next few months
DEADLINE_GRACE_DAYS = 21      # how long an overdue date stays on the panel
# The student handout only carries dates and people that are theirs to see:
# never the counselor's follow-up notes, calendar titles or goal wording.
HANDOUT_KINDS = ('school', 'application', 'decision', 'next_step')
HANDOUT_SUPPORT_KEYS = ('sup_go_to_adult', 'sup_peer_checkin')
# A Dream Act filer can't file a FAFSA (and vice versa): ticking one side
# takes the other side's items off the list.
_AID_ALTERNATES = {'cadaa_submitted': ('fafsa_submitted', 'fsa_ids_created'),
                   'fafsa_submitted': ('cadaa_submitted',)}
# Status ladders for the synced plan fields: a tick never moves a field
# backwards (a 'verified' FAFSA stays verified).
_STATUS_RANK = {
    'fafsa_status': [k for k, _ in CollegeCareerPlan.FAFSA_STATUSES],
    'dream_act_status': [k for k, _ in CollegeCareerPlan.AID_STATUSES],
    'css_profile_status': [k for k, _ in CollegeCareerPlan.AID_STATUSES],
    'personal_statement_status': [k for k, _ in CollegeCareerPlan.STATEMENT_STATUSES],
    'transcript_sent': [False, True],
}


# ── helpers ──────────────────────────────────────────────────────────

def _student(student_id):
    return owned_or_404(Student, student_id, owner_attr='assigned_counselor_id')


def _meeting(meeting_id):
    return owned_or_404(SeniorMeeting, meeting_id)


def _own_meeting(meeting_id):
    """The meeting, and only if the viewer is its counselor: completing,
    reopening and deleting create records in the counselor's own name, so an
    admin's read access doesn't extend to them."""
    m = _meeting(meeting_id)
    if m.counselor_id != current_user.id:
        abort(404)
    return m


def _mine(query):
    """Meetings the viewer can actually open (admins see every counselor's)."""
    if getattr(current_user, 'role', None) == 'admin':
        return query
    return query.filter(SeniorMeeting.counselor_id == current_user.id)


def _is_dict(data):
    return isinstance(data, dict)


def _pathway(student):
    plan = student.college_career_plan
    p = (plan.pathway if plan else None) or 'undecided'
    return p if p in content.PATHWAYS else 'undecided'


def _get_or_create_plan(student):
    plan = student.college_career_plan
    if plan is None:
        plan = CollegeCareerPlan(student_id=student.id, counselor_id=current_user.id,
                                 pathway='undecided')
        db.session.add(plan)
        db.session.flush()
    return plan


def _int_or_none(value, lo=0, hi=10):
    if value in (None, ''):
        return None
    if isinstance(value, bool):
        return None
    try:
        v = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return v if lo <= v <= hi else None


def _text(value, limit):
    return str(value if isinstance(value, (str, int, float)) else '')[:limit]


def _applicable_items(done_keys, pathway, show_all=False):
    """Checklist items for the pathway, minus the other side of an
    either/or pair the student has already done (FAFSA vs. Dream Act)."""
    items = content.CHECKLIST if show_all else content.items_for_pathway(pathway)
    skip = {alt for k, alts in _AID_ALTERNATES.items() if k in done_keys
            for alt in alts if alt not in done_keys}
    return [i for i in items if i['key'] not in skip]


def _checklist_groups(student, pathway, show_all=False):
    """Checklist items for the pathway, grouped, with this student's state."""
    state = {i.key: i for i in student.senior_checklist_items.all()}
    deadlines = {d['key']: d for d in _school_deadlines()}
    done_keys = {k for k, r in state.items() if r.done}
    items = _applicable_items(done_keys, pathway, show_all)
    groups, done, total = [], 0, 0
    for gkey, gtitle in content.CHECKLIST_GROUPS:
        rows = []
        for it in items:
            if it['group'] != gkey:
                continue
            row = state.get(it['key'])
            is_done = bool(row and row.done)
            dl = deadlines.get(it['deadline_key']) if it['deadline_key'] else None
            applies = 'all' in it['pathways'] or pathway in it['pathways']
            rows.append({**it, 'done': is_done,
                         'done_at': row.done_at if row else None,
                         'item_note': row.note if row else '',
                         'deadline': dl['date'] if dl else None,
                         'applies': applies})
            if applies:   # the header count always means "for this pathway"
                total += 1
                done += 1 if is_done else 0
        if rows:
            groups.append({'key': gkey, 'title': gtitle, 'items': rows,
                           'done': sum(1 for r in rows if r['done']), 'total': len(rows)})
    return groups, done, total


def _checklist_counts(student, pathway):
    done_keys = {i.key for i in student.senior_checklist_items.filter(
        SeniorChecklistItem.done == True).all()}  # noqa: E712
    keys = {i['key'] for i in _applicable_items(done_keys, pathway)}
    return len(done_keys & keys), len(keys)


def _school_deadlines():
    """Active school-wide deadlines; the content bank's defaults until any are saved."""
    rows = PostSecondaryDeadline.query.order_by(PostSecondaryDeadline.date).all()
    if rows:   # a school that hid every date gets none, not the defaults back
        return [{'key': r.key, 'label': r.label, 'date': r.date, 'pathways': r.pathway_list,
                 'category': r.category, 'source': r.source, 'note': r.note,
                 'verify': bool(r.verify), 'from_defaults': False}
                for r in rows if r.is_active]
    return [{'key': d['key'], 'label': d['label'], 'date': date.fromisoformat(d['date']),
             'pathways': list(d['pathways']), 'category': d['category'], 'source': d['source'],
             'note': d['note'], 'verify': bool(d['verify']), 'from_defaults': True}
            for d in content.DEADLINE_DEFAULTS]


def _student_deadlines(student, pathway, today=None):
    """Everything with a date that matters to this student, soonest first."""
    today = today or date.today()
    lo = today - timedelta(days=DEADLINE_GRACE_DAYS)
    hi = today + timedelta(days=DEADLINE_HORIZON_DAYS)
    items = []

    def add(kind, label, when, **extra):
        if when is None or when < lo or when > hi:
            return
        items.append({'kind': kind, 'label': label, 'date': when,
                      'days': (when - today).days, **extra})

    for d in _school_deadlines():
        if 'all' in d['pathways'] or pathway in d['pathways']:
            add('school', d['label'], d['date'], key=d['key'], verify=d['verify'],
                category=d['category'], source=d['source'], note=d['note'])
    plan = student.college_career_plan
    if plan:
        for a in plan.applications:
            url = url_for('college_career.edit_application', app_id=a.id)
            if a.status in ('planned', 'planning', 'in_progress', None, ''):
                add('application', f'{a.college_name} application', a.deadline,
                    status=a.status, url=url)
            elif a.decision_date and a.status in ('submitted', 'waitlisted'):
                add('decision', f'{a.college_name} decision expected', a.decision_date, url=url)
    for g in student.goals.filter(Goal.status.in_(('active', 'in_progress'))).all():
        add('goal', g.title, g.target_date, url=url_for('goals.view', id=g.id))
    open_notes = Note.query.filter(
        Note.student_id == student.id, Note.author_id == current_user.id,
        Note.follow_up_needed == True,  # noqa: E712
        db.or_(Note.follow_up_completed == False, Note.follow_up_completed.is_(None)),  # noqa: E712
    ).all()
    for n in open_notes:
        add('follow_up', n.follow_up_notes or n.title or 'Follow-up', n.follow_up_date,
            url=url_for('notes.view_note', id=n.id))
    for ev in CalendarEvent.query.filter(
            CalendarEvent.owner_id == current_user.id, CalendarEvent.student_id == student.id,
            CalendarEvent.event_type == 'deadline', CalendarEvent.status == 'scheduled').all():
        add('calendar', ev.title, ev.start_datetime.date(), url=url_for('calendar.index'))
    prev = (student.senior_meetings.filter(
        SeniorMeeting.counselor_id == current_user.id, SeniorMeeting.status == 'completed',
        SeniorMeeting.next_step_done == False)  # noqa: E712
        .order_by(SeniorMeeting.meeting_date.desc()).first())
    if prev and prev.next_step:
        add('next_step', f'Student step: {prev.next_step[:90]}', prev.next_step_due,
            meeting_id=prev.id, url=url_for('senior_meetings.meeting', meeting_id=prev.id))
    items.sort(key=lambda i: (i['date'], i['kind']))
    return items


def _prompt_sections(kind, show_all=False):
    when = 'any' if show_all else kind
    out = []
    for key, title, subtitle in content.SECTIONS:
        qs = content.questions_for(key, when)
        if qs:
            out.append({'key': key, 'title': title, 'subtitle': subtitle, 'questions': qs})
    return out


def _previous_meeting(student, before):
    """The viewer's most recent completed meeting strictly before ``before``
    (same-day meetings order by id, so a later one is never 'last time')."""
    return (_mine(student.senior_meetings).filter(
        SeniorMeeting.id != before.id, SeniorMeeting.status == 'completed',
        db.or_(SeniorMeeting.meeting_date < before.meeting_date,
               db.and_(SeniorMeeting.meeting_date == before.meeting_date,
                       SeniorMeeting.id < before.id)))
        .order_by(SeniorMeeting.meeting_date.desc(), SeniorMeeting.id.desc()).first())


def _answered(meeting):
    """(question, answer) pairs for every prompt the counselor recorded, in flow order."""
    answers = meeting.answers
    by_key = {q['key']: q for q in content.QUESTIONS}
    order = {k: i for i, (k, _, _) in enumerate(content.SECTIONS)}
    pairs = [(by_key[k], v) for k, v in answers.items()
             if k in by_key and v not in (None, '')]
    pairs.sort(key=lambda p: (order.get(p[0]['section'], 99),
                              content.QUESTION_KEYS.index(p[0]['key'])))
    return pairs


def _asca_touched(meeting):
    counts = Counter()
    domains = Counter()
    for q, _ in _answered(meeting):
        for code in q['asca']:
            counts[code] += 1
        domains[q['domain']] += 1
    codes = [c for c, _ in counts.most_common()]
    domain = domains.most_common(1)[0][0] if domains else 'career'
    return codes, domain


def _asca_field(codes, limit=100):
    """Comma list of whole codes that fits Note.asca_standard (no mid-code cut)."""
    out = ''
    for c in codes:
        nxt = f'{out}, {c}' if out else c
        if len(nxt) > limit:
            break
        out = nxt
    return out


def _summary_text(meeting, student, previous=None):
    """Plain-text record of the meeting: the Note body and the Copy button."""
    label = dict(CollegeCareerPlan.PATHWAYS).get(meeting.pathway or '', 'Undecided')
    lines = [f'Senior / Post-Secondary Meeting - {meeting.meeting_date.isoformat()} '
             f'({meeting.kind_label})'
             + (f' - {meeting.duration_minutes} min' if meeting.duration_minutes else ''),
             f'Pathway: {label}']
    scales = []
    if meeting.scale_plan is not None:
        s = f'plan handled {meeting.scale_plan}/10'
        if previous is not None and previous.scale_plan is not None:
            s += f' (last time {previous.scale_plan}/10)'
        scales.append(s)
    if meeting.scale_stress is not None:
        scales.append(f'stress {meeting.scale_stress}/10')
    if meeting.scale_confidence is not None:
        scales.append(f'confidence in next step {meeting.scale_confidence}/10')
    if scales:
        lines.append('Scaling: ' + '; '.join(scales))
    if (meeting.notes or '').strip():
        lines += ['', 'Notes:', meeting.notes.strip()]
    pairs = _answered(meeting)
    if pairs:
        lines += ['', 'Prompts:']
        for q, a in pairs:
            lines.append(f'- {q["text"]}')
            lines.append(f'  {a}')
    labels = {i['key']: i['label'] for i in content.CHECKLIST}
    checked = [labels[k] for k in meeting.checked_keys if k in labels]
    if checked:
        lines += ['', 'Checked off this meeting: ' + '; '.join(checked)]
    if (meeting.next_step or '').strip():
        lines += ['', "Student's next step: " + meeting.next_step.strip()
                  + (f' (by {meeting.next_step_due.isoformat()})' if meeting.next_step_due else '')]
    if meeting.follow_up_date:
        lines.append(f'Counselor follow-up: {meeting.follow_up_date.isoformat()}'
                     + (f' - {meeting.follow_up_notes.strip()}' if (meeting.follow_up_notes or '').strip() else ''))
    codes, _ = _asca_touched(meeting)
    if codes:
        lines.append('ASCA Mindsets & Behaviors: ' + ', '.join(codes))
    return '\n'.join(lines)


def _sync_plan_field(student, item, done, row):
    """Mirror a checked box onto the College & Career plan field it stands for.

    A tick never moves the field backwards; it records what it changed on
    the checklist row, and an un-tick puts exactly that back."""
    if not item['maps_to']:
        return
    field, value = item['maps_to']
    if done:
        plan = _get_or_create_plan(student)
        ladder = _STATUS_RANK.get(field, [])
        current = getattr(plan, field, None)
        if current not in ladder:
            current = ladder[0] if ladder else current
        if ladder.index(current) >= ladder.index(value):
            return   # already there or further along
        prev = {field: getattr(plan, field, None)}
        if field == 'fafsa_status':
            prev['fafsa_submitted_date'] = (plan.fafsa_submitted_date.isoformat()
                                            if plan.fafsa_submitted_date else None)
            plan.fafsa_submitted_date = plan.fafsa_submitted_date or date.today()
        setattr(plan, field, value)
        row.synced_prev = json.dumps(prev)
    else:
        plan = student.college_career_plan
        if not plan or not row.synced_prev:
            return
        try:
            prev = json.loads(row.synced_prev)
        except (TypeError, ValueError):
            prev = {}
        row.synced_prev = None
        if not isinstance(prev, dict) or getattr(plan, field, None) != value:
            return   # someone changed it since; leave it alone
        setattr(plan, field, prev.get(field))
        if field == 'fafsa_status' and 'fafsa_submitted_date' in prev:
            d = prev['fafsa_submitted_date']
            plan.fafsa_submitted_date = date.fromisoformat(d) if d else None


def _sync_follow_up_event(m, note):
    """Keep the calendar reminder in step with the meeting's follow-up date:
    create it, move it, or remove it. Returns True when one was created."""
    ev = m.follow_up_event
    if ev and ev.status == 'cancelled':
        ev = None
    if not m.follow_up_date:
        if m.follow_up_event:
            db.session.delete(m.follow_up_event)
            m.follow_up_event_id = None
        return False
    if ev is None:
        ev = _create_follow_up_event(note)
        if ev:
            db.session.flush()
            m.follow_up_event_id = ev.id
        return ev is not None
    start_dt = datetime.combine(m.follow_up_date, datetime.min.time().replace(hour=9))
    ev.start_datetime = start_dt
    ev.end_datetime = start_dt + timedelta(minutes=30)
    ev.description = note.follow_up_notes or ev.description
    return False


def _create_follow_up_event(note):
    from app.routes.notes import _create_follow_up_event as make_event
    return make_event(note)


# ── roster ───────────────────────────────────────────────────────────

@senior_meetings_bp.route('/')
@login_required
def index():
    today = date.today()
    grades = request.args.get('grades', '12')
    grade_list = [11, 12] if grades == 'all' else [12]
    only = request.args.get('only', '')
    students = (Student.query
                .filter_by(assigned_counselor_id=current_user.id, status='active')
                .filter(Student.is_sample == False)  # noqa: E712
                .filter(Student.grade_level.in_(grade_list))
                .order_by(Student.last_name, Student.first_name).all())
    ids = [s.id for s in students]

    meetings = (_mine(SeniorMeeting.query).filter(SeniorMeeting.student_id.in_(ids))
                .order_by(SeniorMeeting.meeting_date.desc(), SeniorMeeting.id.desc()).all()
                if ids else [])
    latest, open_by_student, last_done = {}, {}, {}
    for m in meetings:
        latest.setdefault(m.student_id, m)
        if m.status != 'completed':
            open_by_student.setdefault(m.student_id, m)
        elif m.student_id not in last_done:
            last_done[m.student_id] = m

    school = _school_deadlines()
    apps_by_student = {}
    if ids:
        for a, sid in (db.session.query(CollegeApplication, CollegeCareerPlan.student_id)
                       .join(CollegeCareerPlan, CollegeApplication.plan_id == CollegeCareerPlan.id)
                       .filter(CollegeCareerPlan.student_id.in_(ids),
                               CollegeApplication.deadline.isnot(None),
                               CollegeApplication.deadline >= today).all()):
            if a.status in ('planned', 'planning', 'in_progress', None, ''):
                apps_by_student.setdefault(sid, []).append(a)

    rows = []
    for s in students:
        pathway = _pathway(s)
        done, total = _checklist_counts(s, pathway)
        nxt = None
        for d in school:
            if d['date'] >= today and ('all' in d['pathways'] or pathway in d['pathways']):
                nxt = {'label': d['label'], 'date': d['date'], 'kind': 'school'}
                break
        for a in apps_by_student.get(s.id, []):
            if nxt is None or a.deadline < nxt['date']:
                nxt = {'label': f'{a.college_name} application', 'date': a.deadline, 'kind': 'application'}
        last = last_done.get(s.id)
        row = {
            'student': s, 'pathway': pathway,
            'pathway_label': dict(CollegeCareerPlan.PATHWAYS).get(pathway, 'Undecided'),
            'latest': latest.get(s.id), 'open': open_by_student.get(s.id), 'last_done': last,
            'meetings': sum(1 for m in meetings if m.student_id == s.id and m.status == 'completed'),
            'done': done, 'total': total,
            'pct': round(done / total * 100) if total else 0,
            'next_deadline': nxt,
            'step_overdue': bool(last and last.next_step and not last.next_step_done
                                 and last.next_step_due and last.next_step_due < today),
        }
        if only == 'never_met' and row['meetings']:
            continue
        if only == 'no_pathway' and pathway != 'undecided':
            continue
        if only == 'open_step' and not (last and last.next_step and not last.next_step_done):
            continue
        if only == 'in_progress' and not row['open']:
            continue
        rows.append(row)

    upcoming = [d for d in school if d['date'] >= today][:6]
    return render_template('senior_meetings/index.html', rows=rows, grades=grades, only=only,
                           upcoming=upcoming, today=today,
                           total_students=len(students),
                           never_met=sum(1 for r in rows if not r['meetings']),
                           from_defaults=bool(school and school[0]['from_defaults']))


# ── per-student history ──────────────────────────────────────────────

@senior_meetings_bp.route('/student/<int:student_id>')
@login_required
def student(student_id):
    s = _student(student_id)
    pathway = _pathway(s)
    show_all = request.args.get('all') == '1'
    groups, done, total = _checklist_groups(s, pathway, show_all=show_all)
    meetings = _mine(s.senior_meetings).order_by(
        SeniorMeeting.meeting_date.desc(), SeniorMeeting.id.desc()).all()
    open_meeting = next((m for m in meetings if m.status != 'completed'), None)
    return render_template('senior_meetings/student.html', student=s, pathway=pathway,
                           pathway_label=dict(CollegeCareerPlan.PATHWAYS).get(pathway, 'Undecided'),
                           groups=groups, done=done, total=total, show_all=show_all,
                           meetings=meetings, open_meeting=open_meeting,
                           deadlines=_student_deadlines(s, pathway), today=date.today())


@senior_meetings_bp.route('/student/<int:student_id>/start', methods=['POST'])
@login_required
def start(student_id):
    s = _student(student_id)
    existing = _mine(s.senior_meetings).filter(SeniorMeeting.status != 'completed').first()
    if existing:
        flash('Picking up the meeting you already had open.', 'info')
        return redirect(url_for('senior_meetings.meeting', meeting_id=existing.id))
    prior = _mine(s.senior_meetings).filter(SeniorMeeting.status == 'completed').count()
    m = SeniorMeeting(student_id=s.id, counselor_id=current_user.id,
                      meeting_date=date.today(),
                      meeting_kind='followup' if prior else 'first',
                      pathway=_pathway(s))
    db.session.add(m)
    db.session.commit()
    log_action('create', 'senior_meeting', m.id, f'Senior meeting for student #{s.id}')
    return redirect(url_for('senior_meetings.meeting', meeting_id=m.id))


# ── the meeting page ─────────────────────────────────────────────────

@senior_meetings_bp.route('/<int:meeting_id>')
@login_required
def meeting(meeting_id):
    m = _meeting(meeting_id)
    s = m.student
    pathway = m.pathway if m.pathway in content.PATHWAYS else _pathway(s)
    show_all_prompts = request.args.get('prompts') == 'all'
    show_all_items = request.args.get('items') == 'all'
    groups, done, total = _checklist_groups(s, pathway, show_all=show_all_items)
    previous = _previous_meeting(s, m)
    readonly = m.status == 'completed'
    summary = _summary_text(m, s, previous) if readonly else ''
    codes, _ = _asca_touched(m)
    log_action('view', 'senior_meeting', m.id, f'Senior meeting for student #{s.id}')
    return render_template(
        'senior_meetings/meeting.html', meeting=m, student=s, pathway=pathway,
        pathways=CollegeCareerPlan.PATHWAYS, plan=s.college_career_plan,
        sections=_prompt_sections(m.meeting_kind or 'first', show_all_prompts),
        show_all_prompts=show_all_prompts, show_all_items=show_all_items,
        groups=groups, done=done, total=total,
        deadlines=_student_deadlines(s, pathway), previous=previous,
        readonly=readonly, summary=summary, asca=content.ASCA_STANDARDS,
        asca_touched=codes, scale_columns=SCALE_COLUMNS, note_types=NOTE_TYPES,
        handout_support_keys=HANDOUT_SUPPORT_KEYS, is_owner=(m.counselor_id == current_user.id),
        today=date.today(), answers=m.answers, checked=set(m.checked_keys))


@senior_meetings_bp.route('/api/<int:meeting_id>/save', methods=['POST'])
@csrf.exempt
@login_required
def api_save(meeting_id):
    m = _meeting(meeting_id)
    if m.status == 'completed':
        return jsonify({'ok': False, 'error': 'This meeting is completed. Reopen it to edit.'}), 409
    data = request.get_json(silent=True) or {}
    if not _is_dict(data):
        return jsonify({'ok': False, 'error': 'Bad request'}), 400
    s = m.student
    kind = m.meeting_kind or 'first'
    q_when = {q['key']: q['when'] for q in content.QUESTIONS}

    if 'notes' in data:
        m.notes = _text(data.get('notes'), 20000)
    if isinstance(data.get('answers'), dict):
        answers = m.answers
        for key, value in data['answers'].items():
            if not isinstance(key, str) or key not in content.QUESTION_KEYS:
                continue
            if value in (None, '') or not isinstance(value, (str, int, float)):
                answers.pop(key, None)
                value = None
            else:
                answers[key] = str(value)[:4000]
            col = SCALE_COLUMNS.get(key)
            if col and q_when.get(key) in ('any', kind):
                setattr(m, col, _int_or_none(value))
        m.answers = answers
    for col in ('scale_plan', 'scale_stress', 'scale_confidence'):
        if col in data:
            setattr(m, col, _int_or_none(data[col]))
    if isinstance(data.get('pathway'), str) and data['pathway'] in content.PATHWAYS:
        m.pathway = data['pathway']
        if s.college_career_plan or data['pathway'] != 'undecided':
            _get_or_create_plan(s).pathway = data['pathway']
    if 'next_step' in data:
        m.next_step = _text(data.get('next_step'), 2000)
    if 'next_step_due' in data:
        m.next_step_due = parse_date(_text(data.get('next_step_due'), 20))
    if 'follow_up_date' in data:
        m.follow_up_date = parse_date(_text(data.get('follow_up_date'), 20))
    if 'follow_up_notes' in data:
        m.follow_up_notes = _text(data.get('follow_up_notes'), 2000)
    if isinstance(data.get('note_type'), str) and data['note_type'] in dict(NOTE_TYPES):
        m.note_type = data['note_type']
    if 'duration_minutes' in data:
        m.duration_minutes = _int_or_none(data['duration_minutes'], 1, 600)
    if 'meeting_date' in data:
        m.meeting_date = parse_date(_text(data.get('meeting_date'), 20)) or m.meeting_date
    db.session.commit()
    return jsonify({'ok': True, 'saved_at': datetime.now(timezone.utc).isoformat(),
                    'scale_plan': m.scale_plan, 'scale_stress': m.scale_stress,
                    'scale_confidence': m.scale_confidence})


@senior_meetings_bp.route('/api/student/<int:student_id>/checklist', methods=['POST'])
@csrf.exempt
@login_required
def api_checklist(student_id):
    s = _student(student_id)
    data = request.get_json(silent=True) or {}
    if not _is_dict(data):
        return jsonify({'ok': False, 'error': 'Bad request'}), 400
    key = data.get('key')
    item = next((i for i in content.CHECKLIST if i['key'] == key), None)
    if item is None:
        return jsonify({'ok': False, 'error': 'Unknown checklist item.'}), 400
    done = bool(data.get('done'))
    meeting_id = _int_or_none(data.get('meeting_id'), 1, 2 ** 31)
    m = None
    if meeting_id:
        m = db.session.get(SeniorMeeting, meeting_id)
        if not m or m.student_id != s.id or (
                m.counselor_id != current_user.id and getattr(current_user, 'role', None) != 'admin'):
            abort(404)

    row = SeniorChecklistItem.query.filter_by(student_id=s.id, key=key).first()
    if row is None:
        row = SeniorChecklistItem(student_id=s.id, key=key)
        db.session.add(row)
    row.done = done
    row.done_at = datetime.now(timezone.utc) if done else None
    row.meeting_id = m.id if (done and m) else (None if not done else row.meeting_id)
    if 'note' in data:
        row.note = _text(data.get('note'), 300)
    _sync_plan_field(s, item, done, row)
    if m and m.status != 'completed':
        keys = set(m.checked_keys)
        (keys.add if done else keys.discard)(key)
        m.checked_keys = keys
    db.session.commit()
    pathway = (m.pathway if m and m.pathway in content.PATHWAYS else _pathway(s))
    done_n, total_n = _checklist_counts(s, pathway)
    return jsonify({'ok': True, 'key': key, 'done': done, 'counts': {'done': done_n, 'total': total_n},
                    'synced': item['maps_to'][0] if item['maps_to'] else None})


@senior_meetings_bp.route('/api/<int:meeting_id>/step-done', methods=['POST'])
@csrf.exempt
@login_required
def api_step_done(meeting_id):
    """Mark the student's next step from a PREVIOUS meeting as done (or not)."""
    m = _own_meeting(meeting_id)
    data = request.get_json(silent=True) or {}
    if not _is_dict(data):
        return jsonify({'ok': False, 'error': 'Bad request'}), 400
    m.next_step_done = bool(data.get('done', True))
    db.session.commit()
    return jsonify({'ok': True, 'done': m.next_step_done})


@senior_meetings_bp.route('/<int:meeting_id>/complete', methods=['POST'])
@login_required
def complete(meeting_id):
    m = _own_meeting(meeting_id)
    s = m.student
    if m.duration_minutes is None and m.started_at:
        started = m.started_at if m.started_at.tzinfo else m.started_at.replace(tzinfo=timezone.utc)
        elapsed = int((datetime.now(timezone.utc) - started).total_seconds() // 60)
        m.duration_minutes = max(1, min(180, elapsed)) if elapsed >= 1 else None
    previous = _previous_meeting(s, m)
    summary = _summary_text(m, s, previous)
    codes, domain = _asca_touched(m)
    standard = _asca_field(codes)
    kind = 'Follow-up' if m.meeting_kind == 'followup' else 'First meeting'
    if m.note is None:
        note = Note(
            student_id=s.id, author_id=current_user.id,
            note_type=m.note_type or 'college_career',
            title=f'Senior / Post-Secondary Meeting ({kind})',
            content=summary, session_date=m.meeting_date,
            duration_minutes=m.duration_minutes,
            asca_domain=domain, asca_standard=standard,
            delivery_method='in_person', topic_category='Post-secondary planning',
            follow_up_needed=bool(m.follow_up_date), follow_up_date=m.follow_up_date,
            follow_up_notes=(m.follow_up_notes or '') or (
                f'Check in on: {m.next_step}' if m.next_step and m.follow_up_date else ''),
            is_confidential=True,
        )
        db.session.add(note)
        db.session.flush()
        m.note_id = note.id
    else:
        note = m.note
        note.content = summary
        note.note_type = m.note_type or note.note_type
        note.duration_minutes = m.duration_minutes
        note.session_date = m.meeting_date
        note.asca_domain, note.asca_standard = domain, standard
        note.follow_up_needed = bool(m.follow_up_date)
        note.follow_up_date = m.follow_up_date
        note.follow_up_notes = (m.follow_up_notes or '') or (
            f'Check in on: {m.next_step}' if m.next_step and m.follow_up_date else '')
    created_event = _sync_follow_up_event(m, note)
    m.status = 'completed'
    m.completed_at = datetime.now(timezone.utc)
    db.session.commit()
    log_action('update', 'senior_meeting', m.id, f'Completed senior meeting for student #{s.id}')
    msg = 'Meeting saved to the student\'s notes.'
    if created_event:
        msg += ' Follow-up reminder added to your calendar.'
    flash(msg, 'success')
    return redirect(url_for('senior_meetings.meeting', meeting_id=m.id))


@senior_meetings_bp.route('/<int:meeting_id>/reopen', methods=['POST'])
@login_required
def reopen(meeting_id):
    m = _own_meeting(meeting_id)
    m.status = 'in_progress'
    m.completed_at = None
    db.session.commit()
    flash('Meeting reopened. Complete it again when you\'re done to update the note.', 'info')
    return redirect(url_for('senior_meetings.meeting', meeting_id=m.id))


@senior_meetings_bp.route('/<int:meeting_id>/delete', methods=['POST'])
@login_required
def delete(meeting_id):
    m = _own_meeting(meeting_id)
    sid = m.student_id
    SeniorChecklistItem.query.filter_by(meeting_id=m.id).update(
        {'meeting_id': None}, synchronize_session=False)
    kept_note = m.note_id is not None
    db.session.delete(m)
    db.session.commit()
    log_action('delete', 'senior_meeting', meeting_id, f'Senior meeting for student #{sid}')
    flash('Meeting deleted.' + (' The note it created stays in the student\'s timeline.' if kept_note else ''),
          'success')
    return redirect(url_for('senior_meetings.student', student_id=sid))


@senior_meetings_bp.route('/<int:meeting_id>/handout')
@login_required
def handout(meeting_id):
    """A one-page take-home for the student: their step, their dates, what's left."""
    m = _meeting(meeting_id)
    s = m.student
    pathway = m.pathway if m.pathway in content.PATHWAYS else _pathway(s)
    groups, done, total = _checklist_groups(s, pathway)
    season_rank = {'fall': 0, 'winter': 1, 'spring': 2, 'any': 3}
    todo = sorted([i for g in groups for i in g['items'] if not i['done']],
                  key=lambda i: (i['deadline'] or date.max, season_rank.get(i['season'], 9)))[:14]
    deadlines = [d for d in _student_deadlines(s, pathway)
                 if d['days'] >= 0 and d['kind'] in HANDOUT_KINDS][:10]
    support = [a for q, a in _answered(m) if q['key'] in HANDOUT_SUPPORT_KEYS]
    return render_template('senior_meetings/handout.html', meeting=m, student=s,
                           pathway_label=dict(CollegeCareerPlan.PATHWAYS).get(pathway, 'Undecided'),
                           todo=todo, done=done, total=total, deadlines=deadlines,
                           support=support, today=date.today(),
                           school_name=getattr(current_user, 'school_name', '') or '')


# ── school-wide deadlines ────────────────────────────────────────────

@senior_meetings_bp.route('/deadlines')
@login_required
def deadlines():
    rows = PostSecondaryDeadline.query.order_by(
        PostSecondaryDeadline.is_active.desc(), PostSecondaryDeadline.date).all()
    have = {r.key for r in rows if r.key}
    missing = [d for d in content.DEADLINE_DEFAULTS if d['key'] not in have]
    from app.models.user import User
    can_edit = getattr(current_user, 'role', None) == 'admin' or User.query.count() <= 1
    return render_template('senior_meetings/deadlines.html', rows=rows, missing=missing,
                           defaults=content.DEADLINE_DEFAULTS, pathways=CollegeCareerPlan.PATHWAYS,
                           categories=PostSecondaryDeadline.CATEGORIES, today=date.today(),
                           can_edit=can_edit)


@senior_meetings_bp.route('/deadlines', methods=['POST'])
@login_required
@admin_or_sole_user_required
def deadlines_post():
    action = request.form.get('action', '')
    if action == 'load_defaults':
        have = {r.key for r in PostSecondaryDeadline.query.filter(
            PostSecondaryDeadline.key.isnot(None)).all()}
        n = 0
        for d in content.DEADLINE_DEFAULTS:
            if d['key'] in have:
                continue
            db.session.add(PostSecondaryDeadline(
                key=d['key'], label=d['label'], date=date.fromisoformat(d['date']),
                pathways=','.join(d['pathways']), category=d['category'], source=d['source'],
                note=d['note'], verify=bool(d['verify']), created_by_id=current_user.id))
            n += 1
        db.session.commit()
        flash(f'Loaded {n} default deadline{"" if n == 1 else "s"}. Confirm the ones marked "verify".',
              'success')
    elif action in ('add', 'update'):
        row = None
        if action == 'update':
            row = PostSecondaryDeadline.query.get_or_404(request.form.get('id', type=int))
        label = (request.form.get('label') or '').strip()[:200]
        when = parse_date(request.form.get('date'))
        if not label or not when:
            flash('A deadline needs a label and a date.', 'error')
            return redirect(url_for('senior_meetings.deadlines'))
        paths = [p for p in request.form.getlist('pathways') if p in content.PATHWAY_KEYS] or ['all']
        if 'all' in paths:
            paths = ['all']
        if row is None:
            row = PostSecondaryDeadline(created_by_id=current_user.id)
            db.session.add(row)
        row.label, row.date, row.pathways = label, when, ','.join(paths)
        cat = request.form.get('category', 'other')
        row.category = cat if cat in dict(PostSecondaryDeadline.CATEGORIES) else 'other'
        row.source = (request.form.get('source') or '').strip()[:200]
        row.note = (request.form.get('note') or '').strip()[:400]
        row.verify = 'verify' in request.form
        row.is_active = True
        db.session.commit()
        flash('Deadline saved.', 'success')
    elif action in ('delete', 'toggle'):
        row = PostSecondaryDeadline.query.get_or_404(request.form.get('id', type=int))
        if action == 'delete':
            db.session.delete(row)
            flash('Deadline removed.', 'success')
        else:
            row.is_active = not row.is_active
            flash('Deadline ' + ('shown' if row.is_active else 'hidden') + '.', 'success')
        db.session.commit()
    return redirect(url_for('senior_meetings.deadlines'))
