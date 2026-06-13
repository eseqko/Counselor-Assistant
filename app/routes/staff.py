"""Staff directory — teachers and the classes they teach, derived from the
Staff Name column in imported grade data. Read-only and always reflects the
latest import (no separate staff table to keep in sync)."""
from collections import defaultdict
from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from app.models.student import Student
from app.models.grade import GradeRecord

staff_bp = Blueprint('staff', __name__)

_DF = {'F', 'NP', 'D+', 'D', 'D-'}


@staff_bp.route('/')
@login_required
def index():
    """Teacher roster built from grade records on the counselor's caseload."""
    students = Student.query.filter_by(
        assigned_counselor_id=current_user.id, status='active').all()
    student_ids = [s.id for s in students]

    all_grades = []
    if student_ids:
        all_grades = GradeRecord.query.filter(
            GradeRecord.student_id.in_(student_ids),
            GradeRecord.teacher.isnot(None),
            GradeRecord.teacher != '',
            GradeRecord.grade_type == 'final',
        ).all()

    years = sorted({g.school_year for g in all_grades if g.school_year}, reverse=True)
    year = request.args.get('year') or (years[0] if years else '')

    # teacher -> (course, period) -> {students, df, total}
    teachers = defaultdict(lambda: defaultdict(
        lambda: {'students': set(), 'df': 0, 'total': 0}))
    for g in all_grades:
        if year and g.school_year != year:
            continue
        name = (g.teacher or '').strip()
        cell = teachers[name][(g.course_name or 'Unknown', g.period)]
        cell['students'].add(g.student_id)
        cell['total'] += 1
        if (g.letter_grade or '').strip() in _DF:
            cell['df'] += 1

    rows = []
    for name, classes in teachers.items():
        class_list, all_students, total_df, total_grades = [], set(), 0, 0
        for (course, period), c in classes.items():
            class_list.append({
                'course': course, 'period': period,
                'students': len(c['students']), 'df': c['df'], 'total': c['total'],
                'rate': round(c['df'] / c['total'] * 100, 1) if c['total'] else 0,
            })
            all_students |= c['students']
            total_df += c['df']
            total_grades += c['total']
        class_list.sort(key=lambda r: (r['period'] if r['period'] is not None else 99, r['course']))
        rows.append({
            'name': name,
            'classes': class_list,
            'class_count': len(class_list),
            'student_count': len(all_students),
            'df': total_df,
            'rate': round(total_df / total_grades * 100, 1) if total_grades else 0,
        })
    rows.sort(key=lambda r: (-r['student_count'], r['name'].lower()))

    return render_template('staff/index.html', rows=rows, year=year, years=years,
                           has_data=bool(all_grades))
