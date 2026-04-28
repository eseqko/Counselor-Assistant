"""Google Forms API wrapper — create forms from screening templates and import responses."""
from googleapiclient.discovery import build
from app.utils.google_client import get_credentials


def _service(user):
    creds = get_credentials(user)
    if not creds:
        return None
    return build('forms', 'v1', credentials=creds, cache_discovery=False)


def create_form_from_template(user, template):
    """Create a Google Form from a ScreeningTemplate.

    Returns (form_id, form_url) or (None, None) on failure.
    """
    svc = _service(user)
    if not svc:
        return None, None

    form_body = {'info': {'title': template.name}}
    if template.description:
        form_body['info']['documentTitle'] = template.name

    try:
        form = svc.forms().create(body=form_body).execute()
    except Exception:
        return None, None

    form_id = form['formId']
    questions = template.questions
    scoring = template.scoring or {}
    scoring_type = scoring.get('type', 'sum')

    requests = []

    if template.instructions:
        requests.append({
            'createItem': {
                'item': {
                    'title': 'Instructions',
                    'description': template.instructions,
                    'textItem': {},
                },
                'location': {'index': 0},
            }
        })

    offset = 1 if template.instructions else 0

    for i, q in enumerate(questions):
        options = q.get('options', [])

        if len(options) == 2 and all(o.get('value') in (0, 1) for o in options):
            item = _build_radio_item(q, options, i + offset)
        elif options:
            if scoring_type == 'sum':
                item = _build_scale_or_radio_item(q, options, i + offset)
            else:
                item = _build_radio_item(q, options, i + offset)
        else:
            item = _build_radio_item(q, q.get('options', []), i + offset)

        requests.append(item)

    if not requests:
        return form_id, form.get('responderUri', '')

    try:
        svc.forms().batchUpdate(
            formId=form_id,
            body={'requests': requests},
        ).execute()
    except Exception:
        return form_id, form.get('responderUri', '')

    try:
        updated = svc.forms().get(formId=form_id).execute()
        responder_uri = updated.get('responderUri', '')
    except Exception:
        responder_uri = f'https://docs.google.com/forms/d/{form_id}/viewform'

    return form_id, responder_uri


def _build_radio_item(q, options, index):
    choices = []
    for opt in options:
        choices.append({'value': f"{opt['label']}"})

    return {
        'createItem': {
            'item': {
                'title': q['text'],
                'questionItem': {
                    'question': {
                        'required': True,
                        'choiceQuestion': {
                            'type': 'RADIO',
                            'options': choices,
                        },
                    },
                },
            },
            'location': {'index': index},
        }
    }


def _build_scale_or_radio_item(q, options, index):
    values = [o.get('value', 0) for o in options]
    if all(isinstance(v, int) for v in values) and values == list(range(min(values), max(values) + 1)):
        return {
            'createItem': {
                'item': {
                    'title': q['text'],
                    'questionItem': {
                        'question': {
                            'required': True,
                            'scaleQuestion': {
                                'low': min(values),
                                'high': max(values),
                                'lowLabel': options[0]['label'],
                                'highLabel': options[-1]['label'],
                            },
                        },
                    },
                },
                'location': {'index': index},
            }
        }
    return _build_radio_item(q, options, index)


def get_form_responses(user, form_id):
    """Fetch all responses from a Google Form.

    Returns list of dicts: [{question_title: answer_value, ...}, ...]
    """
    svc = _service(user)
    if not svc:
        return []

    try:
        form = svc.forms().get(formId=form_id).execute()
    except Exception:
        return []

    question_map = {}
    for item in form.get('items', []):
        qi = item.get('questionItem')
        if qi and qi.get('question'):
            qid = qi['question']['questionId']
            question_map[qid] = item.get('title', '')

    try:
        resp_data = svc.forms().responses().list(formId=form_id).execute()
    except Exception:
        return []

    results = []
    for response in resp_data.get('responses', []):
        answers = response.get('answers', {})
        row = {'_response_id': response.get('responseId', ''),
               '_submitted': response.get('lastSubmittedTime', '')}
        for qid, answer in answers.items():
            title = question_map.get(qid, qid)
            text_answers = answer.get('textAnswers', {}).get('answers', [])
            if text_answers:
                row[title] = text_answers[0].get('value', '')
            else:
                row[title] = ''
        results.append(row)

    return results


def match_responses_to_template(template, form_responses):
    """Match Google Form responses back to template question IDs for scoring.

    Returns list of dicts with question IDs as keys and integer values.
    """
    questions = template.questions
    title_to_q = {}
    for q in questions:
        title_to_q[q['text'].strip().lower()] = q

    matched = []
    for resp in form_responses:
        row = {}
        for title, answer in resp.items():
            if title.startswith('_'):
                row[title] = answer
                continue
            q = title_to_q.get(title.strip().lower())
            if not q:
                continue
            options = q.get('options', [])
            value = None
            for opt in options:
                if opt['label'].lower() == str(answer).lower():
                    value = opt['value']
                    break
            if value is None:
                try:
                    value = int(answer)
                except (ValueError, TypeError):
                    value = 0
            row[q['id']] = str(value)
        matched.append(row)

    return matched
