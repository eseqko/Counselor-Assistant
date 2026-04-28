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

    google_form_id = db.Column(db.String(200))
    google_form_url = db.Column(db.String(500))

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
    'riasec': {
        'name': 'RIASEC Career Interest Assessment (Holland Codes)',
        'short_name': 'RIASEC',
        'description': 'Based on John Holland\'s theory of career choice. Identifies a student\'s top interest areas across 6 types: Realistic, Investigative, Artistic, Social, Enterprising, and Conventional.',
        'instructions': 'For each activity below, indicate how much you would enjoy doing it.',
        'category': 'career',
        'questions': [
            {'id': 'r1', 'text': 'Build or repair things with your hands', 'dimension': 'realistic'},
            {'id': 'r2', 'text': 'Work outdoors with plants or animals', 'dimension': 'realistic'},
            {'id': 'r3', 'text': 'Operate tools, machines, or vehicles', 'dimension': 'realistic'},
            {'id': 'r4', 'text': 'Build furniture, shelves, or other structures', 'dimension': 'realistic'},
            {'id': 'r5', 'text': 'Work on cars, bikes, or engines', 'dimension': 'realistic'},
            {'id': 'r6', 'text': 'Cook or prepare food from scratch', 'dimension': 'realistic'},
            {'id': 'r7', 'text': 'Set up and troubleshoot technology or equipment', 'dimension': 'realistic'},
            {'id': 'i1', 'text': 'Research a scientific topic in depth', 'dimension': 'investigative'},
            {'id': 'i2', 'text': 'Solve complex math or logic puzzles', 'dimension': 'investigative'},
            {'id': 'i3', 'text': 'Conduct experiments and analyze results', 'dimension': 'investigative'},
            {'id': 'i4', 'text': 'Study how the human body works', 'dimension': 'investigative'},
            {'id': 'i5', 'text': 'Investigate why something happened — find root causes', 'dimension': 'investigative'},
            {'id': 'i6', 'text': 'Use data or statistics to answer a question', 'dimension': 'investigative'},
            {'id': 'i7', 'text': 'Learn about new technologies or discoveries', 'dimension': 'investigative'},
            {'id': 'a1', 'text': 'Draw, paint, or create digital art', 'dimension': 'artistic'},
            {'id': 'a2', 'text': 'Write stories, poems, or songs', 'dimension': 'artistic'},
            {'id': 'a3', 'text': 'Act in a play or create videos', 'dimension': 'artistic'},
            {'id': 'a4', 'text': 'Design graphics, websites, or clothing', 'dimension': 'artistic'},
            {'id': 'a5', 'text': 'Play a musical instrument or sing', 'dimension': 'artistic'},
            {'id': 'a6', 'text': 'Take photos or make films', 'dimension': 'artistic'},
            {'id': 'a7', 'text': 'Decorate spaces or arrange displays', 'dimension': 'artistic'},
            {'id': 's1', 'text': 'Help a friend work through a problem', 'dimension': 'social'},
            {'id': 's2', 'text': 'Tutor or teach someone a skill', 'dimension': 'social'},
            {'id': 's3', 'text': 'Volunteer in the community', 'dimension': 'social'},
            {'id': 's4', 'text': 'Mediate conflicts between people', 'dimension': 'social'},
            {'id': 's5', 'text': 'Work as part of a team to solve a problem', 'dimension': 'social'},
            {'id': 's6', 'text': 'Care for children, elderly, or people who are sick', 'dimension': 'social'},
            {'id': 's7', 'text': 'Plan events or organize group activities', 'dimension': 'social'},
            {'id': 'e1', 'text': 'Start a business or sell something', 'dimension': 'enterprising'},
            {'id': 'e2', 'text': 'Lead a group project or club', 'dimension': 'enterprising'},
            {'id': 'e3', 'text': 'Give a speech or presentation', 'dimension': 'enterprising'},
            {'id': 'e4', 'text': 'Negotiate or debate an issue', 'dimension': 'enterprising'},
            {'id': 'e5', 'text': 'Convince others to see your point of view', 'dimension': 'enterprising'},
            {'id': 'e6', 'text': 'Set goals and develop plans to reach them', 'dimension': 'enterprising'},
            {'id': 'e7', 'text': 'Manage money, budgets, or investments', 'dimension': 'enterprising'},
            {'id': 'c1', 'text': 'Organize files, data, or records', 'dimension': 'conventional'},
            {'id': 'c2', 'text': 'Create spreadsheets or databases', 'dimension': 'conventional'},
            {'id': 'c3', 'text': 'Follow detailed instructions step by step', 'dimension': 'conventional'},
            {'id': 'c4', 'text': 'Proofread documents for accuracy', 'dimension': 'conventional'},
            {'id': 'c5', 'text': 'Keep careful track of schedules or deadlines', 'dimension': 'conventional'},
            {'id': 'c6', 'text': 'Handle paperwork or forms accurately', 'dimension': 'conventional'},
            {'id': 'c7', 'text': 'Use software to manage projects or information', 'dimension': 'conventional'},
        ],
        'options': [
            {'label': 'Dislike', 'value': 0},
            {'label': 'Slightly Enjoy', 'value': 1},
            {'label': 'Enjoy', 'value': 2},
            {'label': 'Strongly Enjoy', 'value': 3},
        ],
        'scoring': {
            'type': 'dimensions',
            'dimensions': ['realistic', 'investigative', 'artistic', 'social', 'enterprising', 'conventional'],
            'dimension_labels': {
                'realistic': 'Realistic (Doers)',
                'investigative': 'Investigative (Thinkers)',
                'artistic': 'Artistic (Creators)',
                'social': 'Social (Helpers)',
                'enterprising': 'Enterprising (Persuaders)',
                'conventional': 'Conventional (Organizers)',
            },
            'dimension_codes': {
                'realistic': 'R', 'investigative': 'I', 'artistic': 'A',
                'social': 'S', 'enterprising': 'E', 'conventional': 'C',
            },
            'dimension_descriptions': {
                'realistic': 'Prefers hands-on, physical work. Careers: engineering, trades, agriculture, athletics, law enforcement.',
                'investigative': 'Prefers research, analysis, and problem-solving. Careers: science, medicine, technology, mathematics.',
                'artistic': 'Prefers creative, unstructured expression. Careers: visual/performing arts, writing, design, media.',
                'social': 'Prefers helping, teaching, and counseling. Careers: education, healthcare, social work, counseling.',
                'enterprising': 'Prefers leading, persuading, and managing. Careers: business, law, politics, sales, management.',
                'conventional': 'Prefers organizing, planning, and accuracy. Careers: accounting, administration, IT, finance, logistics.',
            },
        },
    },
    'career_clusters': {
        'name': 'Career Cluster Interest Survey',
        'short_name': 'Clusters',
        'description': 'Explores interest across the 16 National Career Clusters to help students identify career pathways.',
        'instructions': 'Rate how interested you are in each activity or topic.',
        'category': 'career',
        'questions': [
            {'id': 'ag1', 'text': 'Work on a farm, ranch, or in food production', 'dimension': 'agriculture'},
            {'id': 'ag2', 'text': 'Study environmental science or natural resources', 'dimension': 'agriculture'},
            {'id': 'ar1', 'text': 'Design buildings, landscapes, or public spaces', 'dimension': 'architecture'},
            {'id': 'ar2', 'text': 'Work in construction or skilled trades', 'dimension': 'architecture'},
            {'id': 'av1', 'text': 'Create art, music, video, or multimedia content', 'dimension': 'arts_comm'},
            {'id': 'av2', 'text': 'Work in journalism, broadcasting, or publishing', 'dimension': 'arts_comm'},
            {'id': 'bm1', 'text': 'Manage a business or run a startup', 'dimension': 'business_mgmt'},
            {'id': 'bm2', 'text': 'Oversee operations, HR, or project management', 'dimension': 'business_mgmt'},
            {'id': 'ed1', 'text': 'Teach students in a school setting', 'dimension': 'education'},
            {'id': 'ed2', 'text': 'Work in childcare, coaching, or training', 'dimension': 'education'},
            {'id': 'fi1', 'text': 'Work with money, investments, or banking', 'dimension': 'finance'},
            {'id': 'fi2', 'text': 'Handle accounting, taxes, or financial planning', 'dimension': 'finance'},
            {'id': 'gv1', 'text': 'Work in government, public policy, or law', 'dimension': 'government'},
            {'id': 'gv2', 'text': 'Serve in the military or public safety', 'dimension': 'government'},
            {'id': 'hs1', 'text': 'Provide medical care or therapy to patients', 'dimension': 'health'},
            {'id': 'hs2', 'text': 'Work in a lab, pharmacy, or health technology', 'dimension': 'health'},
            {'id': 'ht1', 'text': 'Work in a hotel, restaurant, or tourism business', 'dimension': 'hospitality'},
            {'id': 'ht2', 'text': 'Plan events, manage recreation, or run a kitchen', 'dimension': 'hospitality'},
            {'id': 'hu1', 'text': 'Counsel individuals or families through problems', 'dimension': 'human_services'},
            {'id': 'hu2', 'text': 'Work in social services, nonprofits, or community outreach', 'dimension': 'human_services'},
            {'id': 'it1', 'text': 'Write code, develop software, or build apps', 'dimension': 'info_tech'},
            {'id': 'it2', 'text': 'Manage networks, databases, or cybersecurity', 'dimension': 'info_tech'},
            {'id': 'lw1', 'text': 'Protect public safety (police, fire, EMS)', 'dimension': 'law_safety'},
            {'id': 'lw2', 'text': 'Work in corrections, security, or legal investigations', 'dimension': 'law_safety'},
            {'id': 'mf1', 'text': 'Operate machinery or work in a factory/plant', 'dimension': 'manufacturing'},
            {'id': 'mf2', 'text': 'Design or improve products and processes', 'dimension': 'manufacturing'},
            {'id': 'mk1', 'text': 'Develop advertising, marketing, or social media campaigns', 'dimension': 'marketing'},
            {'id': 'mk2', 'text': 'Work in retail, e-commerce, or sales', 'dimension': 'marketing'},
            {'id': 'st1', 'text': 'Research in biology, chemistry, physics, or engineering', 'dimension': 'stem'},
            {'id': 'st2', 'text': 'Solve technical or mathematical problems', 'dimension': 'stem'},
            {'id': 'td1', 'text': 'Drive trucks, fly planes, or operate heavy equipment', 'dimension': 'transportation'},
            {'id': 'td2', 'text': 'Work in shipping, logistics, or supply chain', 'dimension': 'transportation'},
        ],
        'options': [
            {'label': 'Not Interested', 'value': 0},
            {'label': 'Slightly Interested', 'value': 1},
            {'label': 'Interested', 'value': 2},
            {'label': 'Very Interested', 'value': 3},
        ],
        'scoring': {
            'type': 'dimensions',
            'dimensions': [
                'agriculture', 'architecture', 'arts_comm', 'business_mgmt',
                'education', 'finance', 'government', 'health',
                'hospitality', 'human_services', 'info_tech', 'law_safety',
                'manufacturing', 'marketing', 'stem', 'transportation',
            ],
            'dimension_labels': {
                'agriculture': 'Agriculture, Food & Natural Resources',
                'architecture': 'Architecture & Construction',
                'arts_comm': 'Arts, A/V Technology & Communications',
                'business_mgmt': 'Business Management & Administration',
                'education': 'Education & Training',
                'finance': 'Finance',
                'government': 'Government & Public Administration',
                'health': 'Health Science',
                'hospitality': 'Hospitality & Tourism',
                'human_services': 'Human Services',
                'info_tech': 'Information Technology',
                'law_safety': 'Law, Public Safety & Security',
                'manufacturing': 'Manufacturing',
                'marketing': 'Marketing, Sales & Service',
                'stem': 'STEM (Science, Technology, Engineering, Math)',
                'transportation': 'Transportation, Distribution & Logistics',
            },
            'dimension_codes': {
                'agriculture': 'AG', 'architecture': 'AC', 'arts_comm': 'AR',
                'business_mgmt': 'BM', 'education': 'ED', 'finance': 'FI',
                'government': 'GV', 'health': 'HS', 'hospitality': 'HT',
                'human_services': 'HU', 'info_tech': 'IT', 'law_safety': 'LW',
                'manufacturing': 'MF', 'marketing': 'MK', 'stem': 'ST',
                'transportation': 'TD',
            },
        },
    },
    'work_values': {
        'name': 'Work Values Inventory',
        'short_name': 'Values',
        'description': 'Based on the O*NET Work Importance Profiler. Helps students identify which work values matter most to them for career satisfaction.',
        'instructions': 'How important is each of the following to you in a future career?',
        'category': 'career',
        'questions': [
            {'id': 'ac1', 'text': 'A job where you can use your best abilities', 'dimension': 'achievement'},
            {'id': 'ac2', 'text': 'Work that gives you a sense of accomplishment', 'dimension': 'achievement'},
            {'id': 'ac3', 'text': 'Being able to see the results of your work', 'dimension': 'achievement'},
            {'id': 'in1', 'text': 'Being free to make your own decisions', 'dimension': 'independence'},
            {'id': 'in2', 'text': 'Working without someone looking over your shoulder', 'dimension': 'independence'},
            {'id': 'in3', 'text': 'Setting your own schedule', 'dimension': 'independence'},
            {'id': 're1', 'text': 'Being recognized for your work by others', 'dimension': 'recognition'},
            {'id': 're2', 'text': 'Being seen as a leader or authority', 'dimension': 'recognition'},
            {'id': 're3', 'text': 'Having your ideas and opinions respected', 'dimension': 'recognition'},
            {'id': 'rl1', 'text': 'Working with friendly, supportive coworkers', 'dimension': 'relationships'},
            {'id': 'rl2', 'text': 'Being able to help other people', 'dimension': 'relationships'},
            {'id': 'rl3', 'text': 'Working as part of a close-knit team', 'dimension': 'relationships'},
            {'id': 'su1', 'text': 'Having a boss who supports and mentors you', 'dimension': 'support'},
            {'id': 'su2', 'text': 'Getting good training and opportunities to learn', 'dimension': 'support'},
            {'id': 'su3', 'text': 'Being treated fairly by your employer', 'dimension': 'support'},
            {'id': 'wc1', 'text': 'Good pay and benefits', 'dimension': 'conditions'},
            {'id': 'wc2', 'text': 'Job security and stability', 'dimension': 'conditions'},
            {'id': 'wc3', 'text': 'Work-life balance and reasonable hours', 'dimension': 'conditions'},
        ],
        'options': [
            {'label': 'Not Important', 'value': 0},
            {'label': 'Somewhat Important', 'value': 1},
            {'label': 'Important', 'value': 2},
            {'label': 'Very Important', 'value': 3},
        ],
        'scoring': {
            'type': 'dimensions',
            'dimensions': ['achievement', 'independence', 'recognition', 'relationships', 'support', 'conditions'],
            'dimension_labels': {
                'achievement': 'Achievement',
                'independence': 'Independence',
                'recognition': 'Recognition',
                'relationships': 'Relationships',
                'support': 'Support',
                'conditions': 'Working Conditions',
            },
            'dimension_codes': {
                'achievement': 'AC', 'independence': 'IN', 'recognition': 'RE',
                'relationships': 'RL', 'support': 'SU', 'conditions': 'WC',
            },
            'dimension_descriptions': {
                'achievement': 'You value work that lets you use your strengths and see meaningful results.',
                'independence': 'You value autonomy — the freedom to decide how, when, and where you work.',
                'recognition': 'You value being respected, visible, and acknowledged for your contributions.',
                'relationships': 'You value positive social connections, teamwork, and helping others.',
                'support': 'You value fair treatment, mentorship, and opportunities for growth.',
                'conditions': 'You value stability, compensation, and a healthy work-life balance.',
            },
        },
    },
    'personality_type': {
        'name': 'Personality Type Indicator (Jungian)',
        'short_name': 'Personality',
        'description': 'Explores personality preferences across four Jungian dimensions: Energy (E/I), Perception (S/N), Decision-making (T/F), and Lifestyle (J/P). Produces a 4-letter type code.',
        'instructions': 'Choose the statement that sounds more like you. Neither answer is wrong — go with your gut.',
        'category': 'career',
        'questions': [
            {'id': 'ei1', 'text': 'At a party, you usually...', 'dimension': 'ei',
             'options': [{'label': 'Talk to many people, including strangers', 'value': 0}, {'label': 'Talk mostly to people you already know', 'value': 1}]},
            {'id': 'ei2', 'text': 'You recharge by...', 'dimension': 'ei',
             'options': [{'label': 'Being around other people', 'value': 0}, {'label': 'Spending time alone', 'value': 1}]},
            {'id': 'ei3', 'text': 'In class, you prefer...', 'dimension': 'ei',
             'options': [{'label': 'Group discussions and activities', 'value': 0}, {'label': 'Working independently or in pairs', 'value': 1}]},
            {'id': 'ei4', 'text': 'When solving a problem, you prefer to...', 'dimension': 'ei',
             'options': [{'label': 'Think out loud with others', 'value': 0}, {'label': 'Think it through quietly first', 'value': 1}]},
            {'id': 'ei5', 'text': 'You would describe yourself as more...', 'dimension': 'ei',
             'options': [{'label': 'Outgoing and action-oriented', 'value': 0}, {'label': 'Reserved and thoughtful', 'value': 1}]},
            {'id': 'sn1', 'text': 'You pay more attention to...', 'dimension': 'sn',
             'options': [{'label': 'Facts and details', 'value': 0}, {'label': 'Patterns and possibilities', 'value': 1}]},
            {'id': 'sn2', 'text': 'You prefer instructions that are...', 'dimension': 'sn',
             'options': [{'label': 'Step-by-step and specific', 'value': 0}, {'label': 'A general outline you can interpret', 'value': 1}]},
            {'id': 'sn3', 'text': 'You trust more in...', 'dimension': 'sn',
             'options': [{'label': 'Your direct experience and what you can observe', 'value': 0}, {'label': 'Your gut feeling and intuition', 'value': 1}]},
            {'id': 'sn4', 'text': 'You are more interested in...', 'dimension': 'sn',
             'options': [{'label': 'What is real and actual right now', 'value': 0}, {'label': 'What could be possible in the future', 'value': 1}]},
            {'id': 'sn5', 'text': 'When reading, you prefer...', 'dimension': 'sn',
             'options': [{'label': 'Literal, straightforward writing', 'value': 0}, {'label': 'Figurative or symbolic writing', 'value': 1}]},
            {'id': 'tf1', 'text': 'When making a decision, you rely more on...', 'dimension': 'tf',
             'options': [{'label': 'Logic and objective analysis', 'value': 0}, {'label': 'Your values and how people will feel', 'value': 1}]},
            {'id': 'tf2', 'text': 'You think it is worse to be...', 'dimension': 'tf',
             'options': [{'label': 'Unfair or inconsistent', 'value': 0}, {'label': 'Unkind or unsympathetic', 'value': 1}]},
            {'id': 'tf3', 'text': 'In an argument, you are more convinced by...', 'dimension': 'tf',
             'options': [{'label': 'Evidence and logical reasoning', 'value': 0}, {'label': 'A sincere, passionate appeal', 'value': 1}]},
            {'id': 'tf4', 'text': 'People who know you would say you are more...', 'dimension': 'tf',
             'options': [{'label': 'Fair and firm', 'value': 0}, {'label': 'Warm and empathetic', 'value': 1}]},
            {'id': 'tf5', 'text': 'When a friend makes a mistake, you tend to...', 'dimension': 'tf',
             'options': [{'label': 'Point out what went wrong so they can fix it', 'value': 0}, {'label': 'Offer support and understanding first', 'value': 1}]},
            {'id': 'jp1', 'text': 'You prefer your days to be...', 'dimension': 'jp',
             'options': [{'label': 'Planned and organized', 'value': 0}, {'label': 'Flexible and spontaneous', 'value': 1}]},
            {'id': 'jp2', 'text': 'Deadlines make you feel...', 'dimension': 'jp',
             'options': [{'label': 'Motivated — you plan ahead to finish early', 'value': 0}, {'label': 'Pressured — you do your best work last minute', 'value': 1}]},
            {'id': 'jp3', 'text': 'Your desk/room is usually...', 'dimension': 'jp',
             'options': [{'label': 'Neat and organized', 'value': 0}, {'label': 'A creative mess with piles', 'value': 1}]},
            {'id': 'jp4', 'text': 'When starting a project, you prefer to...', 'dimension': 'jp',
             'options': [{'label': 'Make a plan before starting', 'value': 0}, {'label': 'Dive in and figure it out as you go', 'value': 1}]},
            {'id': 'jp5', 'text': 'You feel better when things are...', 'dimension': 'jp',
             'options': [{'label': 'Decided and settled', 'value': 0}, {'label': 'Open and flexible', 'value': 1}]},
        ],
        'options': [],
        'scoring': {
            'type': 'personality',
            'axes': [
                {'id': 'ei', 'pole_a': 'E', 'pole_b': 'I', 'label_a': 'Extraversion', 'label_b': 'Introversion',
                 'desc_a': 'Energized by the outer world of people and activity.',
                 'desc_b': 'Energized by the inner world of ideas and reflection.'},
                {'id': 'sn', 'pole_a': 'S', 'pole_b': 'N', 'label_a': 'Sensing', 'label_b': 'Intuition',
                 'desc_a': 'Focuses on concrete facts, details, and present realities.',
                 'desc_b': 'Focuses on patterns, meanings, and future possibilities.'},
                {'id': 'tf', 'pole_a': 'T', 'pole_b': 'F', 'label_a': 'Thinking', 'label_b': 'Feeling',
                 'desc_a': 'Decides with logic, consistency, and objective analysis.',
                 'desc_b': 'Decides with values, empathy, and personal impact.'},
                {'id': 'jp', 'pole_a': 'J', 'pole_b': 'P', 'label_a': 'Judging', 'label_b': 'Perceiving',
                 'desc_a': 'Prefers structure, planning, and closure.',
                 'desc_b': 'Prefers flexibility, spontaneity, and open options.'},
            ],
        },
    },
    'school_connectedness': {
        'name': 'School Connectedness Scale (CDC)',
        'short_name': 'Connectedness',
        'description': 'Brief 5-item scale from the CDC and Add Health study. Measures students\' sense of connection, fairness, and safety at school. Public domain. Higher scores = stronger connectedness.',
        'instructions': 'Indicate how much you agree with each statement about your school.',
        'questions': [
            {'id': 'q1', 'text': 'I feel close to people at this school.'},
            {'id': 'q2', 'text': 'I feel like I am part of this school.'},
            {'id': 'q3', 'text': 'I am happy to be at this school.'},
            {'id': 'q4', 'text': 'The teachers at this school treat students fairly.'},
            {'id': 'q5', 'text': 'I feel safe in my school.'},
        ],
        'options': [
            {'label': 'Strongly Disagree', 'value': 0},
            {'label': 'Disagree', 'value': 1},
            {'label': 'Neutral', 'value': 2},
            {'label': 'Agree', 'value': 3},
            {'label': 'Strongly Agree', 'value': 4},
        ],
        'scoring': {
            'ranges': [
                {'min': 0, 'max': 5, 'label': 'Very Low', 'severity': 'severe', 'action': 'Very low connectedness — prioritize trusted-adult connection, mentoring, and engagement strategies. Investigate barriers (climate, peer relationships, safety).'},
                {'min': 6, 'max': 10, 'label': 'Low', 'severity': 'high', 'action': 'Low connectedness — schedule check-ins, identify a trusted adult, explore clubs/groups, monitor.'},
                {'min': 11, 'max': 15, 'label': 'Moderate', 'severity': 'mild', 'action': 'Moderate connectedness — strengthen weak areas (peer connection, fairness perception, safety).'},
                {'min': 16, 'max': 20, 'label': 'Strong', 'severity': 'minimal', 'action': 'Strong connectedness — protective factor present. Maintain supportive environment.'},
            ],
        },
    },
    'discrimination': {
        'name': 'Brief Perceived Discrimination Scale (School)',
        'short_name': 'Discrimination',
        'description': 'School-adapted brief version of Williams\' Everyday Discrimination Scale. Measures frequency of perceived unfair treatment. Use with care — follow up with conversation about identity attribution and support needs. Higher scores indicate more frequent experiences.',
        'instructions': 'In your day-to-day life at school, how often do these things happen to you?',
        'questions': [
            {'id': 'q1', 'text': 'You are treated with less courtesy or respect than other students.'},
            {'id': 'q2', 'text': 'You receive poorer service or attention than other students at this school.'},
            {'id': 'q3', 'text': 'People act as if they think you are not smart.'},
            {'id': 'q4', 'text': 'People act as if they are afraid of you.'},
            {'id': 'q5', 'text': 'People act as if they think you are dishonest.'},
            {'id': 'q6', 'text': 'You are called names, insulted, threatened, or harassed.'},
            {'id': 'q7', 'text': 'You are treated unfairly or punished more harshly than other students who do the same things.'},
        ],
        'options': [
            {'label': 'Never', 'value': 0},
            {'label': 'Rarely', 'value': 1},
            {'label': 'Sometimes', 'value': 2},
            {'label': 'Often', 'value': 3},
        ],
        'scoring': {
            'ranges': [
                {'min': 0, 'max': 3, 'label': 'Minimal', 'severity': 'minimal', 'action': 'Few or no experiences reported. Maintain inclusive environment.'},
                {'min': 4, 'max': 9, 'label': 'Some', 'severity': 'mild', 'action': 'Some experiences reported — follow up with conversation about context and identity attribution; offer support resources; document for pattern recognition.'},
                {'min': 10, 'max': 14, 'label': 'Frequent', 'severity': 'moderate', 'action': 'Frequent experiences — supportive intervention recommended. Engage trusted adult, document incidents, coordinate with administration if specific actors identified.'},
                {'min': 15, 'max': 21, 'label': 'Pervasive', 'severity': 'severe', 'action': 'Pervasive experiences — coordinated response needed. Advocate with administration, connect to identity-affirming support, monitor mental health (consider PHQ-9/GAD-7), document for accountability.'},
            ],
        },
    },
    'edscls': {
        'name': 'School Climate Survey (EDSCLS-based)',
        'short_name': 'Climate',
        'description': 'Subset of the U.S. Department of Education\'s EDSCLS Student Survey. Measures climate across four equity-relevant dimensions: belonging & respect, cultural diversity, fairness & discipline, and safety. Public domain.',
        'instructions': 'Think about your experience at this school. Indicate how much you agree with each statement.',
        'category': 'climate',
        'questions': [
            {'id': 'b1', 'text': 'Adults at this school care about me.', 'dimension': 'belonging'},
            {'id': 'b2', 'text': 'There is at least one adult at this school I can talk to if I have a problem.', 'dimension': 'belonging'},
            {'id': 'b3', 'text': 'I feel like I belong at this school.', 'dimension': 'belonging'},
            {'id': 'b4', 'text': 'Other students at this school respect me.', 'dimension': 'belonging'},
            {'id': 'b5', 'text': 'I feel comfortable being myself at this school.', 'dimension': 'belonging'},
            {'id': 'd1', 'text': 'Students of all backgrounds are respected at this school.', 'dimension': 'diversity'},
            {'id': 'd2', 'text': 'This school promotes understanding of different cultures.', 'dimension': 'diversity'},
            {'id': 'd3', 'text': 'My culture and background are valued at this school.', 'dimension': 'diversity'},
            {'id': 'd4', 'text': 'I learn about people who are different from me at this school.', 'dimension': 'diversity'},
            {'id': 'd5', 'text': 'Adults at this school treat all students with respect, regardless of their background.', 'dimension': 'diversity'},
            {'id': 'f1', 'text': 'The school rules are fair.', 'dimension': 'fairness'},
            {'id': 'f2', 'text': 'Discipline at this school is consistent — students get the same consequences for the same behavior.', 'dimension': 'fairness'},
            {'id': 'f3', 'text': 'Adults at this school listen to my side of the story before deciding consequences.', 'dimension': 'fairness'},
            {'id': 'f4', 'text': 'I am graded fairly compared to other students.', 'dimension': 'fairness'},
            {'id': 'f5', 'text': 'Students like me get the same opportunities as other students at this school.', 'dimension': 'fairness'},
            {'id': 's1', 'text': 'I feel safe at this school during the day.', 'dimension': 'safety'},
            {'id': 's2', 'text': 'I feel safe traveling to and from this school.', 'dimension': 'safety'},
            {'id': 's3', 'text': 'Bullying is not a problem at this school.', 'dimension': 'safety'},
            {'id': 's4', 'text': 'I would tell an adult at this school if I saw someone being bullied or harassed.', 'dimension': 'safety'},
            {'id': 's5', 'text': 'Adults at this school stop bullying when they see it.', 'dimension': 'safety'},
        ],
        'options': [
            {'label': 'Strongly Disagree', 'value': 0},
            {'label': 'Disagree', 'value': 1},
            {'label': 'Neutral', 'value': 2},
            {'label': 'Agree', 'value': 3},
            {'label': 'Strongly Agree', 'value': 4},
        ],
        'scoring': {
            'type': 'dimensions',
            'dimensions': ['belonging', 'diversity', 'fairness', 'safety'],
            'dimension_labels': {
                'belonging': 'Belonging & Respect',
                'diversity': 'Cultural Diversity',
                'fairness': 'Fairness & Discipline',
                'safety': 'Safety',
            },
            'dimension_codes': {
                'belonging': 'B', 'diversity': 'D', 'fairness': 'F', 'safety': 'S',
            },
            'dimension_descriptions': {
                'belonging': 'Student\'s sense of belonging, supportive adult relationships, and acceptance from peers.',
                'diversity': 'Perception of cultural respect, valuing of differences, and exposure to diverse perspectives.',
                'fairness': 'Perception of consistent rules, fair discipline, equal opportunity, and procedural justice.',
                'safety': 'Physical and emotional safety at school and in transit, bullying climate, and trust in adult response.',
            },
        },
    },
    'aces': {
        'name': 'Adverse Childhood Experiences (ACEs)',
        'short_name': 'ACEs',
        'description': 'Standard 10-item ACE questionnaire (CDC-Kaiser). Screens for trauma exposure before age 18 that correlates with long-term physical and mental health outcomes.',
        'instructions': 'Before your 18th birthday, did you experience any of the following? Answer each question Yes or No. Responses are confidential and used to inform support and resources — not to label or judge.',
        'questions': [
            {'id': 'q1', 'text': 'Did a parent or other adult in the household often or very often swear at you, insult you, put you down, or humiliate you? Or act in a way that made you afraid you might be physically hurt?'},
            {'id': 'q2', 'text': 'Did a parent or other adult in the household often or very often push, grab, slap, or throw something at you? Or ever hit you so hard that you had marks or were injured?'},
            {'id': 'q3', 'text': 'Did an adult or person at least 5 years older than you ever touch or fondle you in a sexual way, have you touch their body in a sexual way, or attempt or actually have sexual contact with you?'},
            {'id': 'q4', 'text': 'Did you often or very often feel that no one in your family loved you or thought you were important or special? Or that your family didn\'t look out for each other, feel close to each other, or support each other?'},
            {'id': 'q5', 'text': 'Did you often or very often feel that you didn\'t have enough to eat, had to wear dirty clothes, had no one to protect you? Or that your parents were too drunk or high to take care of you or take you to the doctor if needed?'},
            {'id': 'q6', 'text': 'Were your parents ever separated or divorced?'},
            {'id': 'q7', 'text': 'Was your mother or stepmother often or very often pushed, grabbed, slapped, or had something thrown at her? Or sometimes, often, or very often kicked, bitten, hit with a fist, or hit with something hard? Or ever repeatedly hit for at least a few minutes or threatened with a gun or knife?'},
            {'id': 'q8', 'text': 'Did you live with anyone who was a problem drinker or alcoholic, or who used street drugs?'},
            {'id': 'q9', 'text': 'Was a household member depressed or mentally ill, or did a household member attempt suicide?'},
            {'id': 'q10', 'text': 'Did a household member go to prison?'},
        ],
        'options': [
            {'label': 'No', 'value': 0},
            {'label': 'Yes', 'value': 1},
        ],
        'scoring': {
            'ranges': [
                {'min': 0, 'max': 0, 'label': 'No ACEs', 'severity': 'none', 'action': 'No ACE exposure reported. Reinforce protective factors.'},
                {'min': 1, 'max': 3, 'label': 'Low-Moderate', 'severity': 'low', 'action': 'Some adversity reported. Build resilience; monitor; consider supportive counseling.'},
                {'min': 4, 'max': 6, 'label': 'High', 'severity': 'high', 'action': 'Significant ACE exposure — strong correlation with health/behavioral risks. Refer to trauma-informed support; coordinate with family/care team.'},
                {'min': 7, 'max': 10, 'label': 'Very High', 'severity': 'severe', 'action': 'Extensive trauma exposure. Prioritize trauma-informed care, mental health referral, and wraparound services. Assess for safety and immediate needs.'},
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
