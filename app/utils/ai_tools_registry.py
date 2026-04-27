"""Config-driven AI Tools registry — each tool is a dict, zero new code to add tools."""

CATEGORIES = {
    'crisis_safety': {'label': 'Crisis & Safety', 'icon': '&#128680;', 'order': 1},
    'sel_classroom': {'label': 'SEL & Classroom', 'icon': '&#128154;', 'order': 2},
    'parent_communication': {'label': 'Parent & Communication', 'icon': '&#128172;', 'order': 3},
    'college_career': {'label': 'College & Career', 'icon': '&#127891;', 'order': 4},
    'documentation': {'label': 'Documentation', 'icon': '&#128203;', 'order': 5},
    'professional': {'label': 'Professional', 'icon': '&#128188;', 'order': 6},
}

AI_TOOLS = [
    # ── Crisis & Safety ──
    {
        'id': 'crisis_intervention_script',
        'title': 'Crisis Intervention Script',
        'description': 'Generate a step-by-step crisis intervention script tailored to the situation.',
        'icon': '&#9888;',
        'category': 'crisis_safety',
        'supports_student_context': True,
        'inputs': [
            {'name': 'crisis_type', 'label': 'Crisis Type', 'type': 'select',
             'options': ['Suicidal ideation', 'Self-harm', 'Abuse/neglect disclosure',
                         'Substance abuse', 'Grief/loss', 'Family crisis',
                         'School violence threat', 'Other'],
             'required': True},
            {'name': 'details', 'label': 'Situation Details', 'type': 'textarea',
             'placeholder': 'Describe what you know about the situation...', 'required': True},
            {'name': 'age_group', 'label': 'Age Group', 'type': 'select',
             'options': ['Elementary (K-5)', 'Middle (6-8)', 'High (9-12)'], 'required': False},
        ],
        'system_prompt': (
            'You are a school crisis intervention specialist. Generate a structured, '
            'step-by-step crisis response script. Include: immediate safety assessment, '
            'de-escalation language, documentation requirements, mandatory reporting '
            'considerations, and follow-up plan. Be specific and actionable. '
            'Follow district and state protocols. Never minimize the situation.'
        ),
        'prompt_template': (
            'Generate a crisis intervention script for the following situation:\n\n'
            'Crisis Type: {crisis_type}\n'
            'Age Group: {age_group}\n'
            'Situation Details: {details}\n'
            '{student_context}'
        ),
    },
    {
        'id': 'suicide_risk_screening',
        'title': 'Suicide Risk Screening Guide',
        'description': 'Create a guided screening protocol with appropriate questions and response steps.',
        'icon': '&#128737;',
        'category': 'crisis_safety',
        'supports_student_context': True,
        'inputs': [
            {'name': 'referral_source', 'label': 'Referral Source', 'type': 'select',
             'options': ['Self-referral', 'Teacher referral', 'Peer referral',
                         'Parent referral', 'Staff observation', 'Other'],
             'required': True},
            {'name': 'observed_behaviors', 'label': 'Observed Behaviors/Concerns', 'type': 'textarea',
             'placeholder': 'What behaviors or statements prompted this screening?', 'required': True},
        ],
        'system_prompt': (
            'You are a school counselor crisis specialist. Generate a suicide risk '
            'screening guide using evidence-based approaches (Columbia Protocol / QPR). '
            'Include: screening questions in appropriate order, risk level assessment '
            'criteria, immediate safety planning steps, parent notification guidance, '
            'referral resources, and documentation template. Always err on the side of '
            'safety. Include the National Suicide Prevention Lifeline: 988.'
        ),
        'prompt_template': (
            'Create a suicide risk screening guide for this situation:\n\n'
            'Referral Source: {referral_source}\n'
            'Observed Behaviors/Concerns: {observed_behaviors}\n'
            '{student_context}'
        ),
    },
    {
        'id': 'mandated_reporting_helper',
        'title': 'Mandated Reporting Documentation',
        'description': 'Help document and organize information for a mandated report.',
        'icon': '&#128221;',
        'category': 'crisis_safety',
        'supports_student_context': True,
        'inputs': [
            {'name': 'report_type', 'label': 'Report Type', 'type': 'select',
             'options': ['Physical abuse', 'Emotional abuse', 'Sexual abuse',
                         'Neglect', 'Domestic violence exposure', 'Other'],
             'required': True},
            {'name': 'observations', 'label': 'Your Observations', 'type': 'textarea',
             'placeholder': 'What did you observe or what was disclosed to you?', 'required': True},
            {'name': 'state', 'label': 'State', 'type': 'text',
             'placeholder': 'e.g. California', 'required': False},
        ],
        'system_prompt': (
            'You are helping a school counselor document a mandated report. '
            'Organize the information clearly for submission to Child Protective Services. '
            'Include: factual observations (no interpretations), direct quotes where applicable, '
            'timeline of events, involved parties, actions already taken, and reporting '
            'checklist. Remind the counselor of their legal obligation and timeline requirements. '
            'Never advise NOT reporting — when in doubt, report.'
        ),
        'prompt_template': (
            'Help me organize a mandated report:\n\n'
            'Report Type: {report_type}\n'
            'State: {state}\n'
            'Observations: {observations}\n'
            '{student_context}'
        ),
    },

    # ── SEL & Classroom ──
    {
        'id': 'sel_lesson_plan',
        'title': 'SEL Lesson Plan Generator',
        'description': 'Create a structured social-emotional learning lesson plan.',
        'icon': '&#127891;',
        'category': 'sel_classroom',
        'supports_student_context': False,
        'inputs': [
            {'name': 'topic', 'label': 'SEL Topic', 'type': 'select',
             'options': ['Self-awareness', 'Self-management', 'Social awareness',
                         'Relationship skills', 'Responsible decision-making',
                         'Conflict resolution', 'Emotion regulation', 'Empathy',
                         'Growth mindset', 'Anti-bullying'],
             'required': True},
            {'name': 'grade_band', 'label': 'Grade Band', 'type': 'select',
             'options': ['K-2', '3-5', '6-8', '9-12'], 'required': True},
            {'name': 'duration', 'label': 'Duration (minutes)', 'type': 'select',
             'options': ['20', '30', '45', '60'], 'required': True},
            {'name': 'group_size', 'label': 'Group Size', 'type': 'select',
             'options': ['Individual', 'Small group (4-8)', 'Classroom (20-35)',
                         'Large group (35+)'],
             'required': False},
        ],
        'system_prompt': (
            'You are a school counselor curriculum designer. Create a detailed, '
            'ready-to-deliver SEL lesson plan aligned with CASEL competencies. '
            'Include: learning objectives, ASCA Mindsets & Behaviors standards, '
            'materials needed, warm-up activity, main activity with step-by-step '
            'instructions, discussion questions, closing/reflection, and assessment.'
        ),
        'prompt_template': (
            'Create an SEL lesson plan:\n\n'
            'Topic: {topic}\nGrade Band: {grade_band}\n'
            'Duration: {duration} minutes\nGroup Size: {group_size}\n'
        ),
    },
    {
        'id': 'group_counseling_curriculum',
        'title': 'Group Counseling Curriculum',
        'description': 'Design a multi-session group counseling series.',
        'icon': '&#128101;',
        'category': 'sel_classroom',
        'supports_student_context': False,
        'inputs': [
            {'name': 'group_topic', 'label': 'Group Topic', 'type': 'select',
             'options': ['Grief/loss', 'Anxiety management', 'Anger management',
                         'Social skills', 'Divorce/family changes', 'Self-esteem',
                         'Study skills', 'Transition support', 'Friendship skills'],
             'required': True},
            {'name': 'num_sessions', 'label': 'Number of Sessions', 'type': 'select',
             'options': ['4', '6', '8', '10'], 'required': True},
            {'name': 'grade_band', 'label': 'Grade Band', 'type': 'select',
             'options': ['K-2', '3-5', '6-8', '9-12'], 'required': True},
        ],
        'system_prompt': (
            'You are a school counselor designing a group counseling curriculum. '
            'Create a full multi-session outline with: group norms, session-by-session '
            'plan (objective, activity, discussion, closure), pre/post assessment, '
            'parent consent letter template, and ASCA alignment. Make activities '
            'age-appropriate and evidence-based.'
        ),
        'prompt_template': (
            'Design a group counseling curriculum:\n\n'
            'Topic: {group_topic}\nSessions: {num_sessions}\n'
            'Grade Band: {grade_band}\n'
        ),
    },
    {
        'id': 'coping_activity_generator',
        'title': 'Coping Skills Activity',
        'description': 'Generate a mindfulness or coping skills activity for students.',
        'icon': '&#129496;',
        'category': 'sel_classroom',
        'supports_student_context': False,
        'inputs': [
            {'name': 'focus_area', 'label': 'Focus Area', 'type': 'select',
             'options': ['Anxiety/worry', 'Anger', 'Sadness', 'Test stress',
                         'Social pressure', 'Mindfulness', 'Grounding',
                         'Breathing exercises'],
             'required': True},
            {'name': 'grade_band', 'label': 'Grade Band', 'type': 'select',
             'options': ['K-2', '3-5', '6-8', '9-12'], 'required': True},
            {'name': 'setting', 'label': 'Setting', 'type': 'select',
             'options': ['Office (1-on-1)', 'Small group', 'Classroom'],
             'required': False},
        ],
        'system_prompt': (
            'You are a school counselor specializing in coping skills and mindfulness. '
            'Create a ready-to-use activity with: clear instructions, materials needed '
            '(keep minimal), step-by-step walkthrough, debrief questions, and a '
            'take-home tip the student can use independently. Make it engaging and '
            'age-appropriate.'
        ),
        'prompt_template': (
            'Create a coping skills activity:\n\n'
            'Focus: {focus_area}\nGrade Band: {grade_band}\n'
            'Setting: {setting}\n'
        ),
    },

    # ── Parent & Communication ──
    {
        'id': 'parent_meeting_talking_points',
        'title': 'Parent Meeting Talking Points',
        'description': 'Generate organized talking points for a parent/guardian meeting.',
        'icon': '&#128172;',
        'category': 'parent_communication',
        'supports_student_context': True,
        'inputs': [
            {'name': 'meeting_purpose', 'label': 'Meeting Purpose', 'type': 'select',
             'options': ['Academic concerns', 'Behavioral concerns', 'Attendance issues',
                         'College planning', 'IEP/504 discussion', 'Crisis follow-up',
                         'Transition planning', 'General check-in'],
             'required': True},
            {'name': 'key_concerns', 'label': 'Key Concerns to Address', 'type': 'textarea',
             'placeholder': 'What specific issues need to be discussed?', 'required': True},
            {'name': 'tone', 'label': 'Tone', 'type': 'select',
             'options': ['Collaborative', 'Supportive', 'Direct/urgent', 'Celebratory'],
             'required': False},
        ],
        'system_prompt': (
            'You are a school counselor preparing for a parent meeting. '
            'Create organized talking points with: opening/rapport builder, '
            'data points to share, key concerns framed constructively, '
            'questions to ask the parent, proposed action steps, and '
            'closing/next steps. Use strength-based language.'
        ),
        'prompt_template': (
            'Prepare talking points for a parent meeting:\n\n'
            'Purpose: {meeting_purpose}\nTone: {tone}\n'
            'Key Concerns: {key_concerns}\n'
            '{student_context}'
        ),
    },
    {
        'id': 'difficult_conversation_script',
        'title': 'Difficult Conversation Script',
        'description': 'Get a script for navigating a sensitive conversation with parents or staff.',
        'icon': '&#128488;',
        'category': 'parent_communication',
        'supports_student_context': True,
        'inputs': [
            {'name': 'audience', 'label': 'Who is the conversation with?', 'type': 'select',
             'options': ['Parent/Guardian', 'Teacher', 'Administrator',
                         'Student', 'Outside agency'],
             'required': True},
            {'name': 'topic', 'label': 'Sensitive Topic', 'type': 'select',
             'options': ['Suspected abuse/neglect', 'Mental health concerns',
                         'Substance use', 'Academic failure', 'Behavioral escalation',
                         'Bullying (victim)', 'Bullying (aggressor)',
                         'Gender identity/sexuality', 'Homelessness',
                         'Suicidal ideation disclosure'],
             'required': True},
            {'name': 'context', 'label': 'Additional Context', 'type': 'textarea',
             'placeholder': 'Any relevant background...', 'required': False},
        ],
        'system_prompt': (
            'You are a school counselor communication coach. Create a sensitive '
            'conversation script with: opening statement, key phrases to use, '
            'phrases to avoid, anticipated reactions and responses, de-escalation '
            'language if needed, and concrete next steps. Use trauma-informed, '
            'culturally responsive language throughout.'
        ),
        'prompt_template': (
            'Help me script a difficult conversation:\n\n'
            'Audience: {audience}\nTopic: {topic}\n'
            'Context: {context}\n'
            '{student_context}'
        ),
    },
    {
        'id': 'parent_email_draft',
        'title': 'Parent Email Draft',
        'description': 'Draft a professional email to parents/guardians.',
        'icon': '&#9993;',
        'category': 'parent_communication',
        'supports_student_context': True,
        'inputs': [
            {'name': 'email_purpose', 'label': 'Email Purpose', 'type': 'select',
             'options': ['Meeting request', 'Follow-up from meeting',
                         'Attendance concern', 'Academic update', 'Positive news',
                         'Resource sharing', 'Event invitation',
                         'College/career update', 'Behavioral concern'],
             'required': True},
            {'name': 'key_points', 'label': 'Key Points to Include', 'type': 'textarea',
             'placeholder': 'What needs to be communicated?', 'required': True},
            {'name': 'language', 'label': 'Language', 'type': 'select',
             'options': ['English', 'English + Spanish translation'],
             'required': False},
        ],
        'system_prompt': (
            'You are a school counselor drafting a professional email. '
            'Write a clear, warm, and professional email. Include: subject line, '
            'greeting, body with key information, call to action, and signature block. '
            'Keep it concise. If Spanish translation is requested, provide both versions.'
        ),
        'prompt_template': (
            'Draft a parent email:\n\n'
            'Purpose: {email_purpose}\nLanguage: {language}\n'
            'Key Points: {key_points}\n'
            '{student_context}'
        ),
    },

    # ── College & Career ──
    {
        'id': 'recommendation_letter',
        'title': 'Recommendation Letter Draft',
        'description': 'Draft a college recommendation letter based on student data.',
        'icon': '&#9997;',
        'category': 'college_career',
        'supports_student_context': True,
        'inputs': [
            {'name': 'college_type', 'label': 'College Type', 'type': 'select',
             'options': ['Highly selective', 'Selective', 'Moderate',
                         'Open admission', 'Scholarship application'],
             'required': True},
            {'name': 'strengths', 'label': 'Key Strengths to Highlight', 'type': 'textarea',
             'placeholder': 'Leadership, resilience, community service, growth...', 'required': True},
            {'name': 'anecdote', 'label': 'Memorable Anecdote (optional)', 'type': 'textarea',
             'placeholder': 'A specific story that illustrates this student...', 'required': False},
        ],
        'system_prompt': (
            'You are a school counselor writing a college recommendation letter. '
            'Write a compelling, authentic letter. Include: how long you have known '
            'the student, academic context, personal qualities with specific examples, '
            'growth narrative, and strong closing endorsement. Vary sentence structure. '
            'Avoid cliches. Make it feel personal, not templated.'
        ),
        'prompt_template': (
            'Draft a college recommendation letter:\n\n'
            'College Type: {college_type}\n'
            'Key Strengths: {strengths}\n'
            'Anecdote: {anecdote}\n'
            '{student_context}'
        ),
    },
    {
        'id': 'personal_statement_feedback',
        'title': 'Personal Statement Feedback',
        'description': 'Provide detailed feedback on a student\'s college essay draft.',
        'icon': '&#128196;',
        'category': 'college_career',
        'supports_student_context': True,
        'inputs': [
            {'name': 'prompt_topic', 'label': 'Essay Prompt/Topic', 'type': 'text',
             'placeholder': 'e.g. Common App Prompt #5', 'required': True},
            {'name': 'essay_draft', 'label': 'Essay Draft', 'type': 'textarea',
             'placeholder': 'Paste the student\'s essay draft here...', 'required': True},
        ],
        'system_prompt': (
            'You are a college essay coach. Provide constructive, encouraging feedback. '
            'Cover: overall impression, narrative structure, voice/authenticity, '
            'specific strengths, areas for improvement with suggestions, word choice, '
            'opening hook, and closing impact. Never rewrite the essay — coach the '
            'student to improve it themselves. Be specific with line-level feedback.'
        ),
        'prompt_template': (
            'Provide feedback on this college essay:\n\n'
            'Prompt/Topic: {prompt_topic}\n\n'
            'Essay Draft:\n{essay_draft}\n'
            '{student_context}'
        ),
    },
    {
        'id': 'financial_aid_explainer',
        'title': 'Financial Aid Explainer',
        'description': 'Generate a plain-language financial aid explanation for families.',
        'icon': '&#128176;',
        'category': 'college_career',
        'supports_student_context': True,
        'inputs': [
            {'name': 'aid_topic', 'label': 'Topic', 'type': 'select',
             'options': ['FAFSA overview', 'CSS Profile', 'Cal Grant (California)',
                         'Dream Act application', 'Scholarship search strategies',
                         'Understanding award letters', 'Work-study explained',
                         'Student loans basics', 'Appeal process'],
             'required': True},
            {'name': 'family_situation', 'label': 'Family Situation (optional)', 'type': 'select',
             'options': ['First-generation college', 'Undocumented student',
                         'Low-income', 'Middle-income', 'Independent student',
                         'Prefer not to specify'],
             'required': False},
        ],
        'system_prompt': (
            'You are a school counselor financial aid specialist. Explain financial '
            'aid concepts in plain, jargon-free language that families can understand. '
            'Include: what it is, who qualifies, step-by-step process, deadlines, '
            'common mistakes to avoid, and helpful resources/links. Be culturally '
            'sensitive and inclusive of all family structures.'
        ),
        'prompt_template': (
            'Create a financial aid explainer:\n\n'
            'Topic: {aid_topic}\n'
            'Family Situation: {family_situation}\n'
            '{student_context}'
        ),
    },

    # ── Documentation ──
    {
        'id': 'bip_draft',
        'title': 'Behavior Intervention Plan Draft',
        'description': 'Generate a draft BIP with target behaviors, interventions, and data collection.',
        'icon': '&#128203;',
        'category': 'documentation',
        'supports_student_context': True,
        'inputs': [
            {'name': 'target_behavior', 'label': 'Target Behavior', 'type': 'textarea',
             'placeholder': 'Describe the behavior of concern...', 'required': True},
            {'name': 'function', 'label': 'Suspected Function', 'type': 'select',
             'options': ['Attention seeking', 'Escape/avoidance', 'Sensory',
                         'Access to tangible', 'Unknown/multiple'],
             'required': True},
            {'name': 'setting', 'label': 'Setting(s)', 'type': 'text',
             'placeholder': 'e.g. Math class, lunch, transitions', 'required': False},
        ],
        'system_prompt': (
            'You are a school counselor/behaviorist drafting a Behavior Intervention Plan. '
            'Include: operational definition of target behavior, baseline data template, '
            'antecedent strategies, replacement behaviors, consequence strategies, '
            'reinforcement schedule, crisis plan if applicable, data collection method, '
            'and review date. Use PBIS-aligned language.'
        ),
        'prompt_template': (
            'Draft a Behavior Intervention Plan:\n\n'
            'Target Behavior: {target_behavior}\n'
            'Suspected Function: {function}\n'
            'Setting: {setting}\n'
            '{student_context}'
        ),
    },
    {
        'id': '504_accommodations',
        'title': '504 Accommodation Suggestions',
        'description': 'Generate appropriate 504 accommodations based on the disability and needs.',
        'icon': '&#9855;',
        'category': 'documentation',
        'supports_student_context': True,
        'inputs': [
            {'name': 'disability', 'label': 'Disability/Condition', 'type': 'select',
             'options': ['ADHD', 'Anxiety disorder', 'Depression', 'Dyslexia',
                         'Diabetes', 'Asthma', 'Visual impairment',
                         'Hearing impairment', 'Physical disability',
                         'Chronic illness', 'Other'],
             'required': True},
            {'name': 'impact_areas', 'label': 'Areas of Impact', 'type': 'textarea',
             'placeholder': 'How does it affect learning? (focus, testing, attendance...)',
             'required': True},
        ],
        'system_prompt': (
            'You are a 504 coordinator suggesting appropriate accommodations. '
            'Provide: categorized accommodations (classroom, testing, behavioral, '
            'environmental), rationale for each, implementation tips for teachers, '
            'and evaluation criteria. Be specific — avoid generic lists. '
            'Match accommodations to the actual functional limitations described.'
        ),
        'prompt_template': (
            'Suggest 504 accommodations:\n\n'
            'Disability/Condition: {disability}\n'
            'Areas of Impact: {impact_areas}\n'
            '{student_context}'
        ),
    },
    {
        'id': 'sst_referral_summary',
        'title': 'SST Referral Summary',
        'description': 'Create a Student Study Team referral summary document.',
        'icon': '&#128220;',
        'category': 'documentation',
        'supports_student_context': True,
        'inputs': [
            {'name': 'reason', 'label': 'Reason for Referral', 'type': 'select',
             'options': ['Academic concerns', 'Behavioral concerns', 'Attendance',
                         'Social-emotional', 'Multiple concerns'],
             'required': True},
            {'name': 'interventions_tried', 'label': 'Interventions Already Tried', 'type': 'textarea',
             'placeholder': 'What has been tried so far?', 'required': True},
            {'name': 'teacher_input', 'label': 'Teacher Input (optional)', 'type': 'textarea',
             'placeholder': 'Any teacher observations or data...', 'required': False},
        ],
        'system_prompt': (
            'You are helping prepare an SST (Student Study Team) referral summary. '
            'Organize: student background, reason for referral, data summary '
            '(grades, attendance, behavior), interventions tried and results, '
            'strengths and areas of concern, and recommended discussion points '
            'for the SST meeting. Use objective, data-driven language.'
        ),
        'prompt_template': (
            'Create an SST referral summary:\n\n'
            'Reason for Referral: {reason}\n'
            'Interventions Tried: {interventions_tried}\n'
            'Teacher Input: {teacher_input}\n'
            '{student_context}'
        ),
    },

    # ── Professional ──
    {
        'id': 'program_audit',
        'title': 'ASCA Program Audit Helper',
        'description': 'Guide you through an ASCA National Model program audit.',
        'icon': '&#128202;',
        'category': 'professional',
        'supports_student_context': False,
        'inputs': [
            {'name': 'component', 'label': 'ASCA Component', 'type': 'select',
             'options': ['Define (Mission/Vision)', 'Manage (Assessments/Tools)',
                         'Deliver (Direct/Indirect Services)',
                         'Assess (Results/Outcomes)', 'Full program review'],
             'required': True},
            {'name': 'current_practices', 'label': 'Current Practices', 'type': 'textarea',
             'placeholder': 'Describe what you currently do in this area...', 'required': True},
        ],
        'system_prompt': (
            'You are an ASCA National Model specialist. Conduct a program audit '
            'for the specified component. Provide: alignment checklist, strengths, '
            'gaps identified, specific recommendations for improvement, sample '
            'language for program documentation, and resources. Reference the '
            'ASCA National Model 4th Edition framework.'
        ),
        'prompt_template': (
            'Help me audit my counseling program:\n\n'
            'ASCA Component: {component}\n'
            'Current Practices: {current_practices}\n'
        ),
    },
    {
        'id': 'results_report_narrative',
        'title': 'Annual Results Report Narrative',
        'description': 'Generate narrative text for your annual counseling results report.',
        'icon': '&#128200;',
        'category': 'professional',
        'supports_student_context': False,
        'inputs': [
            {'name': 'program_area', 'label': 'Program Area', 'type': 'select',
             'options': ['Academic achievement', 'Attendance improvement',
                         'College/career readiness', 'Social-emotional growth',
                         'Discipline/behavior reduction', 'Overall program impact'],
             'required': True},
            {'name': 'data_points', 'label': 'Key Data Points', 'type': 'textarea',
             'placeholder': 'e.g. 85% of seniors completed FAFSA, attendance improved 12%...',
             'required': True},
            {'name': 'interventions_used', 'label': 'Interventions Used', 'type': 'textarea',
             'placeholder': 'What did you do that led to these results?', 'required': True},
        ],
        'system_prompt': (
            'You are helping a school counselor write their annual results report. '
            'Create a professional narrative that: summarizes the program goal, '
            'describes interventions delivered, presents data with context, '
            'discusses outcomes vs. targets, identifies lessons learned, and '
            'proposes next steps. Use data-driven, administrative-friendly language '
            'suitable for presenting to school board or administration.'
        ),
        'prompt_template': (
            'Write an annual results report narrative:\n\n'
            'Program Area: {program_area}\n'
            'Key Data: {data_points}\n'
            'Interventions: {interventions_used}\n'
        ),
    },
]


def get_tool(tool_id):
    for tool in AI_TOOLS:
        if tool['id'] == tool_id:
            return tool
    return None


def get_tools_by_category():
    by_cat = {}
    for tool in AI_TOOLS:
        cat = tool['category']
        if cat not in by_cat:
            by_cat[cat] = []
        by_cat[cat].append(tool)
    ordered = sorted(by_cat.items(), key=lambda x: CATEGORIES.get(x[0], {}).get('order', 99))
    return ordered


def search_tools(query):
    q = query.lower()
    return [t for t in AI_TOOLS if q in t['title'].lower() or q in t['description'].lower()]
