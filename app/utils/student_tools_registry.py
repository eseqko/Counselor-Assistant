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
            'You are a supportive college essay brainstorming coach. Help the student explore '
            'ideas for their personal statement or supplemental essay. Suggest angles, '
            'encourage authentic storytelling, and help them find their unique voice. '
            'Give 3-4 brainstorm directions with brief explanations of why each could work. '
            'Be encouraging and age-appropriate. Do NOT write the essay for them.'
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
            'You are a friendly academic coach helping a high school student create a study plan. '
            'Break the material into manageable chunks across the available days. Include specific '
            'study techniques appropriate to their learning style. Suggest breaks and review sessions. '
            'Be encouraging and practical. Format as a day-by-day plan.'
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
            'You are a compassionate, supportive wellness coach for high school students. '
            'Provide practical, evidence-based coping strategies for the situation described. '
            'Be warm and validating. Suggest 3-5 specific techniques they can try right now. '
            'Include grounding exercises, cognitive reframes, or behavioral strategies as appropriate. '
            'IMPORTANT: If the student describes self-harm, suicidal thoughts, abuse, or a safety concern, '
            'always include: "Please talk to a trusted adult, your school counselor, or call/text 988 '
            '(Suicide & Crisis Lifeline) for immediate support. You are not alone."'
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
            'You are a career exploration coach for high school students. Based on their interests, '
            'skills, and values, suggest 5 career paths they might enjoy. For each career, include: '
            'what the job involves, typical education path, salary range, and why it matches their profile. '
            'Include a mix of traditional and emerging careers. Be enthusiastic and informative. '
            'Mention relevant college majors or CTE pathways.'
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
            'You are a friendly financial aid advisor helping a high school student (or their family) '
            'understand the FAFSA process. Give clear, step-by-step guidance in plain language. '
            'Avoid jargon — explain terms when you use them. Be accurate about current FAFSA '
            'requirements and deadlines. For undocumented students, explain Dream Act / state-level '
            'alternatives. Always encourage them to talk to their school counselor for personalized help.'
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
