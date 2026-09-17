"""Caseload reset: hard-delete a set of students and everything attached.

The app's normal "remove from caseload" is a soft status change, and the
factory reset wipes the whole database (courses, school settings, accounts
included). This sits between them: it clears STUDENT data only — the students
themselves and every record that hangs off them — so a counselor can start a
new year's caseload from a clean slate while keeping the school's catalog,
calendars, staff, templates and their own account.

Deletes are bulk SQL, children before parents, rather than ORM cascades: most
student-linked models declare no cascade, and SQLite doesn't enforce foreign
keys by default, so relying on the ORM would silently leave orphans. IDs are
chunked so a caseload with years of exited students can't exceed SQLite's
bound-parameter limit.
"""
import os

from app import db

_CHUNK = 500


def _chunks(seq):
    for i in range(0, len(seq), _CHUNK):
        yield seq[i:i + _CHUNK]


def _remove_files(directory, names):
    removed = 0
    for name in names:
        if not name:
            continue
        path = os.path.join(directory, name)
        try:
            if os.path.isfile(path):
                os.remove(path)
                removed += 1
        except OSError:
            pass
    return removed


def delete_students_with_dependents(student_ids):
    """Delete the given students and every record attached to them.

    Returns {table_or_label: rows_deleted}. Does NOT commit — the caller owns
    the transaction so a failure part-way leaves nothing changed.
    """
    from app.models.student import Student, student_tags
    from app.models.note import Note
    from app.models.service_record import ServiceRecord
    from app.models.referral import Referral
    from app.models.goal import Goal, GoalProgress
    from app.models.intervention import InterventionPlan, InterventionProgress
    from app.models.grade import GradeRecord
    from app.models.attendance import AttendanceRecord
    from app.models.elpac import ELPACScore
    from app.models.transcript import TranscriptRecord
    from app.models.schedule import ScheduleEntry
    from app.models.document import StudentDocument
    from app.models.consent import ConsentRecord
    from app.models.iep504 import IEP504Record
    from app.models.academic_plan import AcademicPlan
    from app.models.post_grad import PostGradOutcome
    from app.models.college_career import CollegeCareerPlan, CollegeApplication, TestScore
    from app.models.group import GroupMember, GroupAttendance
    from app.models.screening import ScreeningResult
    from app.models.communication import CommunicationLog
    from app.models.calendar_event import CalendarEvent
    from app.models.availability import Booking
    from app.models.ai_tool_history import AIToolHistory
    from app.models.meeting_note import meeting_note_students
    from app.models.senior_meeting import SeniorMeeting, SeniorChecklistItem

    ids = [int(i) for i in student_ids]
    counts = {}
    if not ids:
        return counts

    def add(label, n):
        counts[label] = counts.get(label, 0) + int(n or 0)

    def ids_of(model, id_col, by_col):
        found = []
        for chunk in _chunks(ids):
            found += [r[0] for r in model.query.filter(by_col.in_(chunk))
                      .with_entities(id_col).all()]
        return found

    def bulk(model, col, keys=None):
        for chunk in _chunks(keys if keys is not None else ids):
            add(model.__tablename__,
                model.query.filter(col.in_(chunk)).delete(synchronize_session=False))

    def bulk_table(table, col):
        for chunk in _chunks(ids):
            res = db.session.execute(table.delete().where(col.in_(chunk)))
            add(table.name, res.rowcount)

    # ── files on disk, before the rows that name them go ──
    # Never let a file problem abort the reset: the rows are the record.
    try:
        from app.routes.documents import _docs_dir
        names = ids_of(StudentDocument, StudentDocument.filename, StudentDocument.student_id)
        add('files:student_docs', _remove_files(_docs_dir(), names))
    except Exception:
        pass
    try:
        from app.routes.consents import _consent_dir
        names = ids_of(ConsentRecord, ConsentRecord.document_filename, ConsentRecord.student_id)
        add('files:consents', _remove_files(_consent_dir(), names))
    except Exception:
        pass
    try:
        from app.routes.iep504 import DOCS_DIR
        names = ids_of(IEP504Record, IEP504Record.document_filename, IEP504Record.student_id)
        add('files:iep504', _remove_files(DOCS_DIR, names))
    except Exception:
        pass

    # ── grandchildren: rows that hang off a student-linked row ──
    goal_ids = ids_of(Goal, Goal.id, Goal.student_id)
    if goal_ids:
        bulk(GoalProgress, GoalProgress.goal_id, goal_ids)
    plan_ids = ids_of(CollegeCareerPlan, CollegeCareerPlan.id, CollegeCareerPlan.student_id)
    if plan_ids:
        bulk(CollegeApplication, CollegeApplication.plan_id, plan_ids)
        bulk(TestScore, TestScore.plan_id, plan_ids)
    iv_ids = ids_of(InterventionPlan, InterventionPlan.id, InterventionPlan.student_id)
    if iv_ids:
        bulk(InterventionProgress, InterventionProgress.plan_id, iv_ids)

    # ── rows that point at a student (linkers before what they link to) ──
    for model, col in (
        (SeniorChecklistItem, SeniorChecklistItem.student_id),   # points at meetings
        (SeniorMeeting, SeniorMeeting.student_id),               # points at notes
        (ScreeningResult, ScreeningResult.student_id),
        (Referral, Referral.student_id),
        (InterventionPlan, InterventionPlan.student_id),
        (Goal, Goal.student_id),
        (Note, Note.student_id),
        (ServiceRecord, ServiceRecord.student_id),
        (GradeRecord, GradeRecord.student_id),
        (AttendanceRecord, AttendanceRecord.student_id),
        (ELPACScore, ELPACScore.student_id),
        (TranscriptRecord, TranscriptRecord.student_id),
        (ScheduleEntry, ScheduleEntry.student_id),
        (StudentDocument, StudentDocument.student_id),
        (ConsentRecord, ConsentRecord.student_id),
        (IEP504Record, IEP504Record.student_id),
        (AcademicPlan, AcademicPlan.student_id),
        (PostGradOutcome, PostGradOutcome.student_id),
        (CollegeCareerPlan, CollegeCareerPlan.student_id),
        (GroupMember, GroupMember.student_id),
        (GroupAttendance, GroupAttendance.student_id),
        (CommunicationLog, CommunicationLog.student_id),
        (CalendarEvent, CalendarEvent.student_id),
        (Booking, Booking.student_id),
        (AIToolHistory, AIToolHistory.student_id),
    ):
        bulk(model, col)
    bulk_table(meeting_note_students, meeting_note_students.c.student_id)
    bulk_table(student_tags, student_tags.c.student_id)

    # ── the students themselves ──
    bulk(Student, Student.id)
    return counts
