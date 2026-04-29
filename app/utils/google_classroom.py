"""Google Classroom API wrapper — list courses, post assignments with Form links."""
from googleapiclient.discovery import build
from app.utils.google_client import get_credentials


def _service(user):
    creds = get_credentials(user)
    if not creds:
        return None
    return build('classroom', 'v1', credentials=creds, cache_discovery=False)


def list_courses(user, active_only=True):
    """List courses the user teaches or owns.

    Returns list of {id, name, section, state}.
    """
    svc = _service(user)
    if not svc:
        return []

    try:
        params = {'teacherId': 'me', 'pageSize': 50}
        if active_only:
            params['courseStates'] = ['ACTIVE']
        result = svc.courses().list(**params).execute()
    except Exception:
        return []

    courses = []
    for c in result.get('courses', []):
        courses.append({
            'id': c['id'],
            'name': c.get('name', ''),
            'section': c.get('section', ''),
            'state': c.get('courseState', ''),
        })

    return courses


def post_form_to_course(user, course_id, title, description, form_url):
    """Create a Classroom coursework assignment with a Google Form link.

    Returns the coursework dict or None on failure.
    """
    svc = _service(user)
    if not svc:
        return None

    body = {
        'title': title,
        'description': description,
        'workType': 'ASSIGNMENT',
        'state': 'PUBLISHED',
        'materials': [
            {'link': {'url': form_url, 'title': title}},
        ],
    }

    try:
        cw = svc.courses().courseWork().create(
            courseId=course_id, body=body
        ).execute()
        return cw
    except Exception:
        return None


def post_announcement_to_course(user, course_id, text, form_url=None):
    """Post an announcement to a Classroom course, optionally with a Form link.

    Returns the announcement dict or None on failure.
    """
    svc = _service(user)
    if not svc:
        return None

    body = {
        'text': text,
        'state': 'PUBLISHED',
    }

    if form_url:
        body['materials'] = [
            {'link': {'url': form_url, 'title': 'Complete this assessment'}},
        ]

    try:
        ann = svc.courses().announcements().create(
            courseId=course_id, body=body
        ).execute()
        return ann
    except Exception:
        return None
