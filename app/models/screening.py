import json
from app import db
from datetime import datetime, timezone


class ScreeningTemplate(db.Model):
    """A screening tool template (e.g. PHQ-9, GAD-7, SDQ)."""
    __tablename__ = 'screening_templates'

    id = db.Column(db.Integer, primary_key=True)
    counselor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    name = db.Column(db.String(200), nullable=False)
    short_name = db.Column(db.String(40))
    description = db.Column(db.Text)
    instructions = db.Column(db.Text)

    # JSON structure: list of {id, text, options: [{label, value}], type}
    questions_json = db.Column(db.Text, nullable=False, default='[]')
    # JSON structure: scoring rules: { ranges: [{min, max, label, severity, action}] }
    scoring_json = db.Column(db.Text, default='{}')

    is_built_in = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    counselor = db.relationship('User', backref='screening_templates')
    results = db.relationship('ScreeningResult', backref='template',
                              cascade='all, delete-orphan')

    @property
    def questions(self):
        try:
            return json.loads(self.questions_json or '[]')
        except (json.JSONDecodeError, TypeError):
            return []

    @property
    def scoring(self):
        try:
            return json.loads(self.scoring_json or '{}')
        except (json.JSONDecodeError, TypeError):
            return {}


class ScreeningResult(db.Model):
    __tablename__ = 'screening_results'

    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('screening_templates.id'), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    counselor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    administered_date = db.Column(db.Date, nullable=False,
                                  default=lambda: datetime.now(timezone.utc).date(), index=True)
    responses_json = db.Column(db.Text, nullable=False, default='{}')
    total_score = db.Column(db.Integer)
    severity = db.Column(db.String(50))
    interpretation = db.Column(db.Text)

    notes = db.Column(db.Text)
    action_taken = db.Column(db.Text)
    linked_referral_id = db.Column(db.Integer, db.ForeignKey('referrals.id'), nullable=True)
    linked_intervention_id = db.Column(db.Integer, db.ForeignKey('intervention_plans.id'), nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    counselor = db.relationship('User')
    student = db.relationship('Student', backref=db.backref('screening_results', lazy='dynamic',
                              order_by='ScreeningResult.administered_date.desc()'))
    linked_referral = db.relationship('Referral')
    linked_intervention = db.relationship('InterventionPlan')

    @property
    def responses(self):
        try:
            return json.loads(self.responses_json or '{}')
        except (json.JSONDecodeError, TypeError):
            return {}


# Built-in screener catalog (loaded on demand by routes)
BUILTIN_SCREENERS = {
    'phq9': {
        'name': 'PHQ-9 (Depression)',
        'short_name': 'PHQ-9',
        'description': 'Patient Health Questionnaire-9 — depression screener for adolescents/adults.',
        'instructions': 'Over the last 2 weeks, how often have you been bothered by any of the following problems?',
        'questions': [
            {'id': 'q1', 'text': 'Little interest or pleasure in doing things'},
            {'id': 'q2', 'text': 'Feeling down, depressed, or hopeless'},
            {'id': 'q3', 'text': 'Trouble falling or staying asleep, or sleeping too much'},
            {'id': 'q4', 'text': 'Feeling tired or having little energy'},
            {'id': 'q5', 'text': 'Poor appetite or overeating'},
            {'id': 'q6', 'text': 'Feeling bad about yourself or that you are a failure'},
            {'id': 'q7', 'text': 'Trouble concentrating on things'},
            {'id': 'q8', 'text': 'Moving or speaking so slowly others noticed, or the opposite'},
            {'id': 'q9', 'text': 'Thoughts that you would be better off dead or hurting yourself'},
        ],
        'options': [
            {'label': 'Not at all', 'value': 0},
            {'label': 'Several days', 'value': 1},
            {'label': 'More than half the days', 'value': 2},
            {'label': 'Nearly every day', 'value': 3},
        ],
        'scoring': {
            'ranges': [
                {'min': 0, 'max': 4, 'label': 'Minimal', 'severity': 'minimal', 'action': 'Monitor'},
                {'min': 5, 'max': 9, 'label': 'Mild', 'severity': 'mild', 'action': 'Watchful waiting; rescreen'},
                {'min': 10, 'max': 14, 'label': 'Moderate', 'severity': 'moderate', 'action': 'Treatment plan; counseling/pharma'},
                {'min': 15, 'max': 19, 'label': 'Moderately Severe', 'severity': 'moderately_severe', 'action': 'Active treatment'},
                {'min': 20, 'max': 27, 'label': 'Severe', 'severity': 'severe', 'action': 'Immediate treatment'},
            ],
            'flag_question': 'q9',
        },
    },
    'gad7': {
        'name': 'GAD-7 (Anxiety)',
        'short_name': 'GAD-7',
        'description': 'Generalized Anxiety Disorder 7-item scale.',
        'instructions': 'Over the last 2 weeks, how often have you been bothered by the following problems?',
        'questions': [
            {'id': 'q1', 'text': 'Feeling nervous, anxious, or on edge'},
            {'id': 'q2', 'text': 'Not being able to stop or control worrying'},
            {'id': 'q3', 'text': 'Worrying too much about different things'},
            {'id': 'q4', 'text': 'Trouble relaxing'},
            {'id': 'q5', 'text': "Being so restless that it's hard to sit still"},
            {'id': 'q6', 'text': 'Becoming easily annoyed or irritable'},
            {'id': 'q7', 'text': 'Feeling afraid as if something awful might happen'},
        ],
        'options': [
            {'label': 'Not at all', 'value': 0},
            {'label': 'Several days', 'value': 1},
            {'label': 'More than half the days', 'value': 2},
            {'label': 'Nearly every day', 'value': 3},
        ],
        'scoring': {
            'ranges': [
                {'min': 0, 'max': 4, 'label': 'Minimal', 'severity': 'minimal', 'action': 'Monitor'},
                {'min': 5, 'max': 9, 'label': 'Mild', 'severity': 'mild', 'action': 'Monitor; psychoeducation'},
                {'min': 10, 'max': 14, 'label': 'Moderate', 'severity': 'moderate', 'action': 'Possible treatment'},
                {'min': 15, 'max': 21, 'label': 'Severe', 'severity': 'severe', 'action': 'Active treatment'},
            ],
        },
    },
    'columbia': {
        'name': 'Columbia Suicide Severity Rating Scale (Brief)',
        'short_name': 'C-SSRS',
        'description': 'Brief suicide screener — any "yes" warrants further evaluation.',
        'instructions': 'In the past month:',
        'questions': [
            {'id': 'q1', 'text': 'Have you wished you were dead or wished you could go to sleep and not wake up?'},
            {'id': 'q2', 'text': 'Have you actually had any thoughts of killing yourself?'},
            {'id': 'q3', 'text': 'Have you been thinking about how you might do this?'},
            {'id': 'q4', 'text': 'Have you had these thoughts and had some intention of acting on them?'},
            {'id': 'q5', 'text': 'Have you started to work out or worked out the details of how to kill yourself? Do you intend to carry out this plan?'},
            {'id': 'q6', 'text': 'Have you ever done anything, started to do anything, or prepared to do anything to end your life?'},
        ],
        'options': [
            {'label': 'No', 'value': 0},
            {'label': 'Yes', 'value': 1},
        ],
        'scoring': {
            'ranges': [
                {'min': 0, 'max': 0, 'label': 'No risk', 'severity': 'none', 'action': 'No further screening required.'},
                {'min': 1, 'max': 1, 'label': 'Low risk', 'severity': 'low', 'action': 'Monitor; follow-up.'},
                {'min': 2, 'max': 3, 'label': 'Moderate risk', 'severity': 'moderate', 'action': 'Behavioral health referral; safety plan.'},
                {'min': 4, 'max': 6, 'label': 'High risk', 'severity': 'high', 'action': 'Immediate evaluation; do not leave alone; consider 988/911.'},
            ],
            'flag_question': 'q3',
        },
    },
}
