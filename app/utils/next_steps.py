"""Student 360 action-plan engine.

One entry point — build_action_plan(student, grad_data, today) — turns the
student's existing records into (a) an on-track verdict combining the three
research-backed early-warning legs (credits/grades/attendance: Allensworth &
Easton 9th-grade on-track, Attendance Works chronic-absence 10%, Balfanz ABCs)
and (b) a prioritized list of concrete next steps: credit recovery, college
milestones with real deadlines, EL reclassification, compliance reviews,
family-contact recency, and data-freshness warnings.

Pure computation: no new tables, no request context. Everything derives from
records the app already stores; `grad_data` is the output of
graduation._build_student_grad_data so the credit math has exactly one home.
"""
from collections import defaultdict
from datetime import date, timedelta

from app import db
from app.models.grade import GradeRecord, GPA_POINTS
from app.models.attendance import AttendanceRecord

# Letters that mean "no credit earned — retake needed". NM (No Mark) is
# excluded: it carries no pass/fail signal (Pass/No-Mark courses).
FAIL_LETTERS = {'F', 'NP'}

# Core academic subjects for the 9th-grade on-track "core course F" leg.
CORE_SUBJECTS = {'english', 'math', 'mathematics', 'science', 'social science',
                 'social studies', 'history'}

PRIORITY_ORDER = {'critical': 0, 'high': 1, 'medium': 2, 'info': 3}


def _item(priority, category, title, why, action, url=None, due=None):
    return {'priority': priority, 'category': category, 'title': title,
            'why': why, 'action': action, 'url': url,
            'due': due.isoformat() if hasattr(due, 'isoformat') else due}


# ── Attendance (corrected math) ──────────────────────────────────────────────

def student_attendance_stats(student, window_days=365, today=None):
    """Chronic-absence stats with the CORRECT denominator.

    A day counts as enrolled if the student has ANY attendance record that
    day (period-level imports emit rows for present periods too); a day is
    absent if any period that day is 'absent'. Rate = absent days / enrolled
    days — the Attendance Works definition — rather than the old
    present-period-records / total-period-records, which understated absence
    on period-level data and mixed tardies into the denominator.

    Returns {'enrolled_days', 'absent_days', 'rate_pct', 'level', 'monthly'}
    where level is 'chronic' (>=10%), 'at_risk' (>=5%) or 'ok', and monthly
    is an ordered [(label, absent_days, enrolled_days)] series.
    """
    today = today or date.today()
    start = today - timedelta(days=window_days)
    rows = db.session.query(
        AttendanceRecord.date, AttendanceRecord.status,
    ).filter(
        AttendanceRecord.student_id == student.id,
        AttendanceRecord.date >= start,
    ).all()
    if not rows:
        return {'enrolled_days': 0, 'absent_days': 0, 'rate_pct': None,
                'level': 'no_data', 'monthly': []}

    day_status = {}
    for d, status in rows:
        if d is None:
            continue
        s = (status or '').lower()
        day_status.setdefault(d, set()).add(s)

    enrolled = len(day_status)
    absent_days = sum(1 for statuses in day_status.values() if 'absent' in statuses)
    rate = round(100 * absent_days / enrolled, 1) if enrolled else None

    if rate is None:
        level = 'no_data'
    elif rate >= 10:
        level = 'chronic'
    elif rate >= 5:
        level = 'at_risk'
    else:
        level = 'ok'

    monthly = defaultdict(lambda: [0, 0])   # label -> [absent, enrolled]
    for d, statuses in day_status.items():
        label = d.strftime('%Y-%m')
        monthly[label][1] += 1
        if 'absent' in statuses:
            monthly[label][0] += 1
    monthly_series = [(k, v[0], v[1]) for k, v in sorted(monthly.items())]

    return {'enrolled_days': enrolled, 'absent_days': absent_days,
            'rate_pct': rate, 'level': level, 'monthly': monthly_series}


# ── GPA trend ────────────────────────────────────────────────────────────────

def student_gpa_trend(student, max_points=8):
    """Per-quarter GPA series + direction.

    Returns {'series': [{'label': '25-26 Q3', 'gpa': 2.7}], 'direction':
    'improving'|'declining'|'flat'|'insufficient'} using final grades only.
    Direction compares the last two quarters (>=0.15 GPA delta to call it).
    """
    rows = db.session.query(
        GradeRecord.school_year, GradeRecord.quarter, GradeRecord.letter_grade,
    ).filter(
        GradeRecord.student_id == student.id,
        GradeRecord.grade_type == 'final',
        GradeRecord.quarter.isnot(None),
    ).all()
    buckets = defaultdict(list)
    for year, quarter, letter in rows:
        pts = GPA_POINTS.get((letter or '').strip())
        if pts is not None and year:
            buckets[(year, quarter)].append(pts)
    ordered = sorted(buckets.keys())[-max_points:]
    series = []
    for year, quarter in ordered:
        pts = buckets[(year, quarter)]
        short_year = year[2:4] + '-' + year[7:9] if len(year) == 9 else year
        series.append({'label': f'{short_year} Q{quarter}',
                       'gpa': round(sum(pts) / len(pts), 2)})
    if len(series) < 2:
        direction = 'insufficient'
    else:
        delta = series[-1]['gpa'] - series[-2]['gpa']
        direction = ('improving' if delta >= 0.15
                     else 'declining' if delta <= -0.15 else 'flat')
    return {'series': series, 'direction': direction}


# ── Credit velocity ──────────────────────────────────────────────────────────

def student_credit_velocity(student):
    """Credits earned between successive transcript imports.

    Returns {'series': [{'label': quarter-or-date, 'total': completed}],
    'latest_gain': credits added since previous import or None}. Transcript
    snapshots were never diffed anywhere before this.
    """
    records = list(student.transcript_records)     # ordered import_date DESC
    records.reverse()                              # chronological
    series = []
    for tr in records:
        label = tr.quarter or (tr.import_date.strftime('%m/%y') if tr.import_date else '?')
        series.append({'label': label, 'total': tr.total_completed or 0})
    latest_gain = None
    if len(series) >= 2:
        latest_gain = round(series[-1]['total'] - series[-2]['total'], 1)
    return {'series': series[-8:], 'latest_gain': latest_gain}


# ── Failed courses needing recovery ─────────────────────────────────────────

def failed_courses_needing_recovery(student):
    """Final F/NP courses with no later passing retake — credit-recovery list.

    A course is 'recovered' if a strictly later (year, quarter) final record
    of the same course name has a passing letter (credit-earning: D- or
    better, or P).
    """
    rows = db.session.query(
        GradeRecord.course_name, GradeRecord.letter_grade,
        GradeRecord.school_year, GradeRecord.quarter,
    ).filter(
        GradeRecord.student_id == student.id,
        GradeRecord.grade_type == 'final',
    ).all()

    def sort_key(year, quarter):
        return (year or '', quarter or 0)

    failed = {}       # course -> latest fail (year, quarter, letter)
    passed_after = defaultdict(list)   # course -> [(year, quarter)]
    for course, letter, year, quarter in rows:
        course_clean = (course or '').strip()
        lg = (letter or '').strip()
        if not course_clean or not lg:
            continue
        if lg in FAIL_LETTERS:
            key = sort_key(year, quarter)
            if course_clean not in failed or key > sort_key(failed[course_clean][0], failed[course_clean][1]):
                failed[course_clean] = (year, quarter, lg)
        elif lg == 'P' or (GPA_POINTS.get(lg) is not None and GPA_POINTS[lg] > 0):
            passed_after[course_clean].append(sort_key(year, quarter))

    out = []
    for course, (year, quarter, letter) in failed.items():
        fail_key = sort_key(year, quarter)
        if any(p > fail_key for p in passed_after.get(course, [])):
            continue   # recovered later
        out.append({'course': course, 'letter': letter,
                    'year': year, 'quarter': quarter})
    out.sort(key=lambda r: (r['year'] or '', r['quarter'] or 0), reverse=True)
    return out


# ── The action plan ─────────────────────────────────────────────────────────

def build_action_plan(student, grad_data=None, today=None):
    """Assemble the on-track verdict and the prioritized next-step list."""
    today = today or date.today()
    items = []
    factors = []          # (ok: bool, label)

    attendance = student_attendance_stats(student, today=today)
    gpa = student_gpa_trend(student)
    recovery = failed_courses_needing_recovery(student)

    # ── Leg 1: credits / graduation pace (from the single grad engine) ──
    if grad_data:
        risk = grad_data.get('risk') or 'unknown'
        if risk in ('critical', 'at-risk'):
            factors.append((False, f'Credit pace: {risk}'))
        elif risk in ('warning',):
            factors.append((False, 'Credit pace: warning'))
        elif risk == 'on-track':
            factors.append((True, 'Credit pace on track'))
        # Per-subject gaps live in grad_data['credits'] ({subject: {required,
        # completed, need, ...}}); 'subj_shortfall' is the summed total.
        subject_credits = grad_data.get('credits') or {}
        subject_needs = []
        for subj, data in subject_credits.items():
            if subj == 'TOTALS' or not isinstance(data, dict):
                continue
            need = data.get('need')
            if need is None:
                need = max(0, (data.get('required', 0) or 0)
                           - (data.get('completed', 0) or 0))
            if need > 0:
                subject_needs.append((subj, need))
        for subj, need in sorted(subject_needs, key=lambda kv: -kv[1]):
            items.append(_item(
                'high' if risk in ('critical', 'at-risk') else 'medium',
                'credits',
                f'{subj}: {need:g} credits short',
                f'Graduation audit shows {need:g} credits still needed in {subj}.',
                'Plan courses or credit recovery to close the gap.',
                url=f'/academic-plan/student/{student.id}'))
        ag_status = grad_data.get('ag_status')
        if ag_status == 'deficient' and (student.grade_level or 0) >= 11:
            items.append(_item(
                'high', 'college', 'a-g deficient for UC/CSU eligibility',
                'Research benchmark: 11 a-g courses done before senior year.',
                'Review the a-g table and adjust the schedule now.',
                url=f'/graduation/student/{student.id}'))

    # ── Leg 2: course failures / credit recovery ──
    for f in recovery[:6]:
        when = f'{f["year"]} Q{f["quarter"]}' if f['quarter'] else (f['year'] or '')
        items.append(_item(
            'critical' if (student.grade_level or 0) >= 11 else 'high',
            'credits',
            f'Retake {f["course"]}',
            f'Failed ({f["letter"]}) in {when}; no passing retake on record.',
            'Enroll in credit recovery / retake next term.',
            url=f'/academic-plan/student/{student.id}'))
    if recovery:
        factors.append((False, f'{len(recovery)} course{"s" if len(recovery) != 1 else ""} needing recovery'))
    else:
        factors.append((True, 'No unrecovered course failures'))

    # 9th-grade on-track (Allensworth/Easton): >=5 credits per semester pace
    # plus <=1 core-subject F in the current year.
    if (student.grade_level or 0) == 9 and grad_data:
        core_fails = sum(1 for f in recovery
                         if any(c in (f['course'] or '').lower() for c in CORE_SUBJECTS))
        total_completed = grad_data.get('total_completed') or 0
        on_track_9 = total_completed >= 25 and core_fails <= 1
        factors.append((on_track_9, '9th-grade on-track indicator'
                                     + ('' if on_track_9 else ' MISSED')))

    # ── Leg 3: attendance ──
    if attendance['level'] == 'chronic':
        factors.append((False, f'Chronically absent ({attendance["rate_pct"]}%)'))
        items.append(_item(
            'critical', 'attendance',
            f'Chronic absence: {attendance["rate_pct"]}% of days missed',
            f'{attendance["absent_days"]} of {attendance["enrolled_days"]} enrolled days '
            '(Attendance Works threshold is 10%).',
            'Attendance conference + barrier check; consider SART referral.',
            url=f'/caseload/{student.id}'))
    elif attendance['level'] == 'at_risk':
        factors.append((False, f'Attendance at risk ({attendance["rate_pct"]}%)'))
        items.append(_item(
            'high', 'attendance',
            f'Attendance slipping: {attendance["rate_pct"]}% absent',
            f'{attendance["absent_days"]} of {attendance["enrolled_days"]} days; at-risk band is 5-10%.',
            'Early check-in with student and family before it becomes chronic.'))
    elif attendance['level'] == 'ok':
        factors.append((True, f'Attendance healthy ({attendance["rate_pct"]}%)'))

    # ── GPA trajectory ──
    if gpa['direction'] == 'declining':
        last = gpa['series'][-1]
        prev = gpa['series'][-2]
        items.append(_item(
            'high', 'grades',
            f'GPA falling: {prev["gpa"]} → {last["gpa"]}',
            f'Quarter-over-quarter drop ({prev["label"]} → {last["label"]}).',
            'Check in on what changed; loop in teachers of the slipping courses.'))
        factors.append((False, 'GPA declining'))
    elif gpa['direction'] == 'improving':
        factors.append((True, 'GPA improving'))

    # ── College milestones by grade level ──
    plan = student.college_career_plan
    grade = student.grade_level or 0
    if grade in (9, 10):
        if not plan or (plan.pathway == 'undecided' and not plan.career_interest):
            items.append(_item(
                'medium', 'college', 'No career direction on file',
                f'Grade {grade} milestone: explore interests early.',
                'Run a career interest screener (RIASEC) and record a pathway.',
                url='/screenings/'))
        if not getattr(student, 'academic_plan', None):
            items.append(_item(
                'medium', 'college', 'No 4-year academic plan',
                f'Grade {grade} milestone: a plan keeps a-g and credits on rails.',
                'Build the 4-year plan (auto-build available).',
                url=f'/academic-plan/student/{student.id}'))
    if grade >= 11:
        has_test = bool(plan and (plan.sat_total or plan.act_composite
                                  or (plan.test_scores.count() if plan else 0)))
        if not has_test:
            items.append(_item(
                'high' if grade == 12 else 'medium', 'college',
                'No SAT/ACT score on file',
                f'Grade {grade}: testing window matters for many applications.',
                'Register for SAT/ACT (or record scores / test-optional decision).',
                url=f'/college-career/student/{student.id}'))
    if grade == 12:
        if not plan or plan.fafsa_status in (None, '', 'not_started'):
            items.append(_item(
                'critical', 'college', 'FAFSA not started',
                'Senior year: CA priority deadline is March 2 (AB 469 requires '
                'confirmation of completion or opt-out).',
                'Start the FAFSA / CADAA with the family now.',
                url=f'/college-career/student/{student.id}'))
        apps = list(plan.applications) if plan else []
        if not apps:
            items.append(_item(
                'high', 'college', 'No college applications tracked',
                'Senior with no applications on file.',
                'Build the college list and log applications with deadlines.',
                url=f'/college-career/student/{student.id}'))
        for a in apps:
            if a.deadline and a.status in ('planning', 'in_progress', None, ''):
                days = (a.deadline - today).days
                if days < 0:
                    items.append(_item(
                        'critical', 'college',
                        f'{a.college_name}: deadline PASSED',
                        f'Deadline was {a.deadline.strftime("%m/%d/%Y")} and the '
                        f'application is still {a.status or "unstarted"}.',
                        'Confirm status — appeal, switch to rolling, or drop.',
                        url=f'/college-career/student/{student.id}', due=a.deadline))
                elif days <= 30:
                    items.append(_item(
                        'critical' if days <= 14 else 'high', 'college',
                        f'{a.college_name}: due in {days} day{"s" if days != 1 else ""}',
                        f'Application status is {a.status or "unstarted"}.',
                        'Finish and submit the application.',
                        url=f'/college-career/student/{student.id}', due=a.deadline))

    # ── EL reclassification ──
    latest_elpac = student.latest_elpac
    if latest_elpac and latest_elpac.overall_level == 4 and student.el_status != 'RFEP':
        items.append(_item(
            'high', 'el', 'Reclassification candidate (ELPAC PL 4)',
            'Scored Overall Level 4 on the latest ELPAC and is not yet RFEP.',
            'Start reclassification paperwork (teacher evaluation, parent consult).',
            url='/analytics/elpac'))

    # ── Compliance / care ──
    rec = getattr(student, 'iep504_record', None)   # uselist=False relationship
    if rec and rec.next_review_date:
        days = (rec.next_review_date - today).days
        if days <= 30:
            items.append(_item(
                'critical' if days <= 14 else 'high', 'compliance',
                f'{rec.plan_type.upper()} review '
                + (f'OVERDUE by {-days} days' if days < 0 else f'due in {days} days'),
                f'Next review date {rec.next_review_date.strftime("%m/%d/%Y")}.',
                'Schedule the review meeting.',
                url=f'/caseload/{student.id}', due=rec.next_review_date))

    # ── Family contact recency ──
    last_contact = (student.communications.first()
                    if hasattr(student, 'communications') else None)
    if last_contact and last_contact.contact_date:
        days_since = (today - last_contact.contact_date).days
        if days_since > 60:
            items.append(_item(
                'medium', 'family',
                f'No family contact logged in {days_since} days',
                f'Last contact {last_contact.contact_date.strftime("%m/%d/%Y")}.',
                'Reach out and log the touchpoint.',
                url=f'/caseload/{student.id}'))

    # ── Freshness warnings ──
    freshness = []
    latest_tr = student.transcript_records.first()
    if latest_tr and latest_tr.import_date:
        tr_days = (today - latest_tr.import_date.date()).days
        if tr_days > 60:
            freshness.append(_item(
                'info', 'stale', f'Transcript {tr_days} days old',
                f'Last transcript import {latest_tr.import_date.strftime("%m/%d/%Y")} — '
                'credit totals may lag.',
                'Re-import the latest transcript.',
                url='/caseload/transcripts/batch'))
    if attendance['level'] == 'no_data':
        freshness.append(_item(
            'info', 'stale', 'No attendance data on file',
            'Attendance leg of the on-track index cannot be computed.',
            'Import attendance from your SIS.',
            url='/data-import/attendance/upload'))

    # ── Verdict ──
    bad = [label for ok, label in factors if not ok]
    good = [label for ok, label in factors if ok]
    has_critical = any(i['priority'] == 'critical' for i in items)
    if has_critical or len(bad) >= 2:
        verdict = 'off_track'
    elif bad:
        verdict = 'at_risk'
    elif good:
        verdict = 'on_track'
    else:
        verdict = 'unknown'

    items.sort(key=lambda i: (PRIORITY_ORDER.get(i['priority'], 9),
                              i['due'] or '9999', i['title']))

    return {
        'on_track': {'verdict': verdict, 'good': good, 'bad': bad},
        'items': items,
        'freshness': freshness,
        'attendance': attendance,
        'gpa_trend': gpa,
        'credit_velocity': student_credit_velocity(student),
    }
