"""Data import hub page."""
from flask import render_template
from flask_login import login_required, current_user
from app.models.attendance import AttendanceRecord
from app.models.grade import GradeRecord
from app.models.import_log import ImportLog
from app.utils.caseload import caseload_student_ids
from app.routes.data_import import data_import_bp


@data_import_bp.route('/')
@login_required
def index():
    """Data import hub page."""
    student_ids = caseload_student_ids(current_user)
    attendance_count = AttendanceRecord.query.filter(
        AttendanceRecord.student_id.in_(student_ids)).count() if student_ids else 0
    grade_count = GradeRecord.query.filter(
        GradeRecord.student_id.in_(student_ids)).count() if student_ids else 0

    # Last import per type
    last_imports = {}
    for itype in ('attendance', 'grades', 'student_update'):
        log = ImportLog.query.filter_by(
            user_id=current_user.id, import_type=itype
        ).order_by(ImportLog.imported_at.desc()).first()
        if log:
            last_imports[itype] = log

    return render_template('data_import/index.html',
                           attendance_count=attendance_count,
                           grade_count=grade_count,
                           last_imports=last_imports)
