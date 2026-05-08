"""Idempotent demo-data seeder for the USB demo bundle.

Creates the demo counselor user and populates ~25 students with realistic
notes, grades, attendance, goals, referrals, calendar events, and activities.
Reads the canonical dataset from ``data/demo-seed.json`` (relative to the
app's BASE_DIR), which uses day/hour offsets so dates always look fresh.

Safe to call on every app startup — exits early when the demo user exists.
"""
import json
import os
from datetime import datetime, timedelta, time, timezone

from app import db


def _resolve_seed_path():
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    return os.path.join(base, 'data', 'demo-seed.json')


def _date_from_offset(offset_days):
    return (datetime.now(timezone.utc) + timedelta(days=offset_days)).date()


def _datetime_from_offset(offset_hours):
    return datetime.now(timezone.utc) + timedelta(hours=offset_hours)


def _time_from_string(s):
    if not s:
        return None
    h, m = s.split(':')
    return time(int(h), int(m))


def ensure_seeded(app):
    """Seed the demo dataset if not already present. Idempotent."""
    from app.models.user import User

    with app.app_context():
        if User.query.filter_by(username='demo').first():
            return  # already seeded

        seed_path = _resolve_seed_path()
        if not os.path.isfile(seed_path):
            app.logger.warning(f"Demo seed file not found: {seed_path}")
            return

        with open(seed_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        _seed_all(data)
        app.logger.info("Demo data seeded.")


def _seed_all(data):
    from app.models.user import User
    from app.models.student import Student
    from app.models.note import Note
    from app.models.grade import GradeRecord
    from app.models.attendance import AttendanceRecord
    from app.models.goal import Goal
    from app.models.referral import Referral
    from app.models.calendar_event import CalendarEvent
    from app.models.activity import Activity

    demo = User(
        username='demo',
        display_name='Demo Counselor',
        school_name='Lincoln High School (Demo)',
        role='counselor',
        setup_completed=True,
        theme_preference='light',
    )
    demo.set_password('demo')
    db.session.add(demo)
    db.session.flush()  # assigns demo.id

    # Students — keep idx → id mapping for downstream references
    student_ids = []
    for s in data.get('students', []):
        student = Student(
            student_id_number=s['student_id_number'],
            first_name=s['first_name'],
            last_name=s['last_name'],
            grade_level=s.get('grade_level'),
            gender=s.get('gender'),
            ethnicity=s.get('ethnicity'),
            email=s.get('email'),
            phone=s.get('phone'),
            parent_guardian_name=s.get('parent_guardian_name'),
            parent_guardian_phone=s.get('parent_guardian_phone'),
            parent_guardian_email=s.get('parent_guardian_email'),
            homeroom=s.get('homeroom'),
            assigned_counselor_id=demo.id,
            status='active',
            iep_status=s.get('iep_status', False),
            section_504=s.get('section_504', False),
            el_status=s.get('el_status', 'EO'),
            el_level=s.get('el_level'),
        )
        db.session.add(student)
        db.session.flush()
        student_ids.append(student.id)

    def sid(idx):
        return student_ids[idx]

    for n in data.get('notes', []):
        note = Note(
            student_id=sid(n['student_idx']),
            author_id=demo.id,
            note_type=n['note_type'],
            title=n.get('title'),
            content=n['content'],
            session_date=_date_from_offset(n.get('session_date_offset_days', 0)),
            duration_minutes=n.get('duration_minutes'),
            asca_domain=n.get('asca_domain'),
            topic_category=n.get('topic_category'),
            delivery_method=n.get('delivery_method', 'in_person'),
            setting=n.get('setting'),
            outcome=n.get('outcome'),
            follow_up_needed=n.get('follow_up_needed', False),
            follow_up_date=(
                _date_from_offset(n['follow_up_offset_days'])
                if 'follow_up_offset_days' in n else None
            ),
            follow_up_notes=n.get('follow_up_notes'),
            is_confidential=n.get('is_confidential', True),
        )
        db.session.add(note)

    for g in data.get('grades', []):
        db.session.add(GradeRecord(
            student_id=sid(g['student_idx']),
            school_year=g.get('school_year', '2025-2026'),
            quarter=g.get('quarter', 1),
            course_name=g['course_name'],
            course_number=g.get('course_number'),
            period=g.get('period'),
            grade_type=g.get('grade_type', 'final'),
            letter_grade=g.get('letter_grade'),
            percent_grade=g.get('percent_grade'),
            credits_earned=g.get('credits_earned', 5.0),
            credits_attempted=g.get('credits_attempted', 5.0),
            subject_area=g.get('subject_area'),
            is_ag=g.get('is_ag', False),
            is_honors_ap=g.get('is_honors_ap', False),
            is_cte=g.get('is_cte', False),
            imported_by_id=demo.id,
        ))

    for a in data.get('attendance', []):
        db.session.add(AttendanceRecord(
            student_id=sid(a['student_idx']),
            date=_date_from_offset(a['date_offset_days']),
            period=a.get('period'),
            status=a['status'],
            course_name=a.get('course_name'),
            reason=a.get('reason'),
            imported_by_id=demo.id,
        ))

    for goal in data.get('goals', []):
        db.session.add(Goal(
            student_id=sid(goal['student_idx']),
            counselor_id=demo.id,
            title=goal['title'],
            description=goal.get('description'),
            asca_domain=goal.get('asca_domain'),
            asca_mindset=goal.get('asca_mindset'),
            baseline=goal.get('baseline'),
            target=goal.get('target'),
            measurement_method=goal.get('measurement_method'),
            strategy=goal.get('strategy'),
            start_date=_date_from_offset(goal.get('start_offset_days', -30)),
            target_date=_date_from_offset(goal.get('target_offset_days', 60)),
            status=goal.get('status', 'active'),
            progress_percent=goal.get('progress_percent', 0),
        ))

    for r in data.get('referrals', []):
        db.session.add(Referral(
            student_id=sid(r['student_idx']),
            counselor_id=demo.id,
            referral_date=_date_from_offset(r.get('referral_offset_days', -7)),
            referral_type=r['referral_type'],
            referred_to=r['referred_to'],
            contact_info=r.get('contact_info'),
            reason=r['reason'],
            urgency=r.get('urgency', 'routine'),
            status=r.get('status', 'pending'),
            consent_obtained=r.get('consent_obtained', False),
        ))

    for e in data.get('calendar_events', []):
        start = _datetime_from_offset(e['start_offset_hours'])
        end = start + timedelta(minutes=e.get('duration_minutes', 30))
        db.session.add(CalendarEvent(
            owner_id=demo.id,
            title=e['title'],
            description=e.get('description'),
            location=e.get('location'),
            start_datetime=start,
            end_datetime=end,
            event_type=e.get('event_type', 'appointment'),
            student_id=sid(e['student_idx']) if 'student_idx' in e else None,
            status='scheduled',
        ))

    for act in data.get('activities', []):
        db.session.add(Activity(
            counselor_id=demo.id,
            title=act['title'],
            description=act.get('description'),
            date=_date_from_offset(act.get('date_offset_days', -1)),
            start_time=_time_from_string(act.get('start_time')),
            end_time=_time_from_string(act.get('end_time')),
            duration_minutes=act.get('duration_minutes'),
            service_type=act['service_type'],
            category=act.get('category'),
            topic=act.get('topic'),
            delivery_type=act.get('delivery_type'),
            num_students=act.get('num_students', 0),
            grade_levels=act.get('grade_levels'),
        ))

    db.session.commit()


def reset_and_reseed(app):
    """Wipe demo data and re-seed. Used by the /demo-reset route."""
    from app.models.user import User
    from app.models.student import Student
    from app.models.note import Note
    from app.models.grade import GradeRecord
    from app.models.attendance import AttendanceRecord
    from app.models.goal import Goal, GoalProgress
    from app.models.referral import Referral
    from app.models.calendar_event import CalendarEvent
    from app.models.activity import Activity

    with app.app_context():
        demo = User.query.filter_by(username='demo').first()
        if demo:
            student_ids = [
                row[0] for row in db.session.query(Student.id)
                .filter_by(assigned_counselor_id=demo.id).all()
            ]
            if student_ids:
                Note.query.filter(Note.student_id.in_(student_ids)).delete(synchronize_session=False)
                GradeRecord.query.filter(GradeRecord.student_id.in_(student_ids)).delete(synchronize_session=False)
                AttendanceRecord.query.filter(AttendanceRecord.student_id.in_(student_ids)).delete(synchronize_session=False)
                Referral.query.filter(Referral.student_id.in_(student_ids)).delete(synchronize_session=False)
                goal_ids = [g.id for g in Goal.query.filter(Goal.student_id.in_(student_ids)).all()]
                if goal_ids:
                    GoalProgress.query.filter(GoalProgress.goal_id.in_(goal_ids)).delete(synchronize_session=False)
                Goal.query.filter(Goal.student_id.in_(student_ids)).delete(synchronize_session=False)
                CalendarEvent.query.filter(CalendarEvent.student_id.in_(student_ids)).delete(synchronize_session=False)
                Student.query.filter(Student.id.in_(student_ids)).delete(synchronize_session=False)
            Activity.query.filter_by(counselor_id=demo.id).delete(synchronize_session=False)
            CalendarEvent.query.filter_by(owner_id=demo.id).delete(synchronize_session=False)
            db.session.delete(demo)
            db.session.commit()

        seed_path = _resolve_seed_path()
        if os.path.isfile(seed_path):
            with open(seed_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            _seed_all(data)
