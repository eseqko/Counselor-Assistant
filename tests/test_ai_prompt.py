"""Shape of the student-insights AI prompt (grade/quarter/WIP/semester aware)."""
from app.routes.ai import _build_student_insights_prompt, _transcript_credit_gaps


def _prompt_for(app, as_demo_user, sid):
    from app.models.student import Student
    with as_demo_user():
        return _build_student_insights_prompt(Student.query.get(sid))


def test_tenth_grader_on_pace(app, as_demo_user, make_student):
    # Grade 10 Q3 expects 140 credits at the school's 80/yr pace (4 classes x
    # 4 quarters x 5 credits). Previously this fixture used 60+15 and asserted
    # "on pace" against a ~55/yr benchmark of 76 — under the real pace that
    # student cannot reach 225 in the two years left, so the numbers here now
    # describe a genuinely on-pace student.
    sid = make_student(grade=10, completed=120, wip=20, quarter='10-Q3', ag_met=1)
    p = _prompt_for(app, as_demo_user, sid)
    assert '10th grader' in p
    assert 'EXPECTED BY THIS POINT: ~140/225' in p
    assert '120 completed + 20 WIP (projected 140)' in p
    assert 'on pace' in p
    assert 'Spring semester' in p          # Q3 -> Spring
    assert 'Graduation Progress' in p      # grades <=10 framing
    assert 'Risk: ' not in p               # never leak the bare risk label
    assert 'Credit gaps:' not in p         # on-pace 10th grader: no gap dump


def test_ninth_grader_start_of_year_not_doomed(app, as_demo_user, make_student):
    sid = make_student(grade=9, completed=0, wip=30, quarter='9-Q1', ag_met=0)
    p = _prompt_for(app, as_demo_user, sid)
    assert '9th grader' in p
    assert 'Fall semester' in p
    assert 'not on track' not in p.lower()


def test_senior_uses_graduation_framing(app, as_demo_user, make_student):
    sid = make_student(grade=12, completed=200, wip=25, quarter='12-Q4', ag_met=7)
    p = _prompt_for(app, as_demo_user, sid)
    assert 'senior' in p
    assert 'Graduation Status' in p
    assert 'Spring semester' in p


def test_middle_schooler_has_no_benchmark_block(app, as_demo_user, make_student):
    sid = make_student(grade=8, completed=None, wip=None, quarter=None)
    p = _prompt_for(app, as_demo_user, sid)
    assert 'EXPECTED BY THIS POINT' not in p
    assert 'middle school' in p


def test_transcript_credit_gaps_helper():
    import json
    tr = type('TR', (), {'credits_json': json.dumps({
        'English': {'required': 40, 'completed': 20},
        'Math': {'required': 30, 'completed': 30},
        'Science': {'required': 20, 'completed': 5},
    })})()
    gaps = _transcript_credit_gaps(tr)
    assert gaps == {'English': 20, 'Science': 15}   # zero-need subjects omitted
    assert _transcript_credit_gaps(None) == {}
