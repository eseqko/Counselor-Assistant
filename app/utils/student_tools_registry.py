"""Student-facing AI tools — accessible via public portal link."""

STUDENT_TOOLS = [
    {
        'id': 'essay_brainstorm',
        'title': 'College Essay Brainstorm Coach',
        'description': 'Brainstorm ideas and outlines for your college personal statement or supplemental essays.',
        'icon': '&#9997;',
        'inputs': [
            {'name': 'prompt_topic', 'label': 'Essay Prompt or Topic', 'type': 'textarea',
             'placeholder': 'Paste the essay prompt or describe what you want to write about...', 'required': True},
            {'name': 'interests', 'label': 'Your Interests / Strengths', 'type': 'textarea',
             'placeholder': 'What are you passionate about? What makes you unique?', 'required': False},
        ],
        'system_prompt': (
            'You are a college essay brainstorming coach. Suggest 3-4 essay angles '
            'with brief explanations of why each could work. Encourage authentic '
            'storytelling. Do NOT write the essay for them.'
        ),
        'prompt_template': (
            'Essay prompt/topic: {prompt_topic}\n\n'
            'My interests and strengths: {interests}\n\n'
            'Please help me brainstorm ideas for this essay.'
        ),
    },
    {
        'id': 'study_plan',
        'title': 'Study Plan Generator',
        'description': 'Create a personalized study plan for upcoming exams or assignments.',
        'icon': '&#128214;',
        'inputs': [
            {'name': 'subject', 'label': 'Subject / Class', 'type': 'text',
             'placeholder': 'e.g. AP US History, Algebra 2, Biology', 'required': True},
            {'name': 'exam_info', 'label': 'What are you studying for?', 'type': 'textarea',
             'placeholder': 'Describe the test, assignment, or topics you need to study...', 'required': True},
            {'name': 'days_until', 'label': 'Days until the exam/deadline', 'type': 'text',
             'placeholder': 'e.g. 5', 'required': False},
            {'name': 'study_style', 'label': 'How do you learn best?', 'type': 'select',
             'options': ['Visual (diagrams, charts)', 'Reading/Writing', 'Hands-on practice', 'Group study', 'Not sure'],
             'required': False},
        ],
        'system_prompt': (
            'Help a student create a study plan. Break material into daily chunks. '
            'Include study techniques for their learning style. Suggest breaks. '
            'Format as a day-by-day plan. Be encouraging.'
        ),
        'prompt_template': (
            'Subject: {subject}\n'
            'Studying for: {exam_info}\n'
            'Days available: {days_until}\n'
            'Learning style: {study_style}\n\n'
            'Please create a study plan for me.'
        ),
    },
    {
        'id': 'stress_coping',
        'title': 'Stress & Coping Tool',
        'description': 'Get personalized coping strategies for stress, anxiety, or difficult emotions.',
        'icon': '&#128154;',
        'inputs': [
            {'name': 'situation', 'label': 'What\'s going on?', 'type': 'textarea',
             'placeholder': 'Describe what\'s stressing you out or how you\'re feeling...', 'required': True},
            {'name': 'tried', 'label': 'What have you already tried?', 'type': 'textarea',
             'placeholder': 'Any coping strategies you\'ve used before?', 'required': False},
        ],
        'system_prompt': (
            'You are a supportive wellness coach. Suggest 3-5 practical coping techniques '
            'the student can try now. Be warm and validating. '
            'IMPORTANT: If they mention self-harm, suicidal thoughts, or abuse, '
            'always include: "Talk to a trusted adult or call/text 988 for support."'
        ),
        'prompt_template': (
            'What I\'m dealing with: {situation}\n\n'
            'What I\'ve tried: {tried}\n\n'
            'Can you suggest some coping strategies?'
        ),
    },
    {
        'id': 'career_explorer',
        'title': 'Career Interest Explorer',
        'description': 'Discover careers that match your interests, skills, and values.',
        'icon': '&#127919;',
        'inputs': [
            {'name': 'interests', 'label': 'What are you interested in?', 'type': 'textarea',
             'placeholder': 'Subjects you enjoy, hobbies, activities, things you\'re curious about...', 'required': True},
            {'name': 'skills', 'label': 'What are you good at?', 'type': 'textarea',
             'placeholder': 'Skills, talents, things that come naturally to you...', 'required': False},
            {'name': 'values', 'label': 'What matters to you in a career?', 'type': 'select',
             'options': ['Helping people', 'Making money', 'Creativity', 'Working outdoors', 'Technology', 'Leadership', 'Flexibility'],
             'required': False},
        ],
        'system_prompt': (
            'Suggest 5 career paths based on the student\'s interests and skills. '
            'For each: what the job involves, education path, salary range, and '
            'why it fits them. Include traditional and emerging careers.'
        ),
        'prompt_template': (
            'My interests: {interests}\n'
            'My skills: {skills}\n'
            'What matters to me: {values}\n\n'
            'What careers might be a good fit for me?'
        ),
    },
    {
        'id': 'fafsa_guide',
        'title': 'FAFSA Walkthrough Assistant',
        'description': 'Get step-by-step help understanding the FAFSA process.',
        'icon': '&#128176;',
        'inputs': [
            {'name': 'question', 'label': 'What do you need help with?', 'type': 'select',
             'options': [
                 'I don\'t know where to start',
                 'What documents do I need?',
                 'How do I create an FSA ID?',
                 'Help with filling out the application',
                 'My parents are divorced — whose info do I use?',
                 'I\'m undocumented — what are my options?',
                 'What happens after I submit?',
                 'I got my SAR — what do I do?',
             ], 'required': True},
            {'name': 'details', 'label': 'Any additional details?', 'type': 'textarea',
             'placeholder': 'Add any context that might help...', 'required': False},
        ],
        'system_prompt': (
            'Help a student understand the FAFSA process. Give clear, step-by-step '
            'guidance in plain language. Explain terms when used. For undocumented '
            'students, explain Dream Act alternatives. Encourage talking to their counselor.'
        ),
        'prompt_template': (
            'My question: {question}\n\n'
            'Additional details: {details}\n\n'
            'Please walk me through this step by step.'
        ),
    },
]


def get_student_tool(tool_id):
    for t in STUDENT_TOOLS:
        if t['id'] == tool_id:
            return t
    return None
