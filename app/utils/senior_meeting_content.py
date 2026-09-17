"""Content for the Senior / Post-Secondary 1:1 Meeting feature.

Plain data only (lists of dicts and constants) plus two tiny filter helpers
and a pure ``validate()`` self-check. No Flask imports, no I/O.

Written for the 2026-27 school year: seniors graduate June 2027, apply for
Fall 2027 admission, and file for 2027-28 financial aid. Every year-specific
date is a default; entries with ``'verify': True`` should be confirmed each
August before the feature goes live.

Text marked student-facing (``help``, ``text``) is written to be read aloud
to a 17-year-old. ``coach`` lines are for the counselor only.
"""

# ---------------------------------------------------------------------------
# 1. ASCA Student Standards: Mindsets & Behaviors for Student Success (2021)
# ---------------------------------------------------------------------------

ASCA_STANDARDS = {
    # Mindsets
    'M 1': 'Belief in development of whole self, including a healthy balance of mental, social/emotional and physical well-being',
    'M 2': 'Sense of acceptance, respect, support and inclusion for self and others in the school environment',
    'M 3': 'Positive attitude toward work and learning',
    'M 4': 'Self-confidence in ability to succeed',
    'M 5': 'Belief in using abilities to their fullest to achieve high-quality results and outcomes',
    'M 6': 'Understanding that postsecondary education and lifelong learning are necessary for long-term success',
    # Behaviors: Learning Strategies
    'B-LS 1': 'Critical-thinking skills to make informed decisions',
    'B-LS 2': 'Creative approach to learning, tasks and problem solving',
    'B-LS 3': 'Time-management, organizational and study skills',
    'B-LS 4': 'Self-motivation and self-direction for learning',
    'B-LS 5': 'Media and technology skills to enhance learning',
    'B-LS 6': 'High-quality standards for tasks and activities',
    'B-LS 7': 'Long- and short-term academic, career and social/emotional goals',
    'B-LS 8': 'Engagement in challenging coursework',
    'B-LS 9': "Decision-making informed by gathering evidence, getting others' perspectives and recognizing personal bias",
    'B-LS 10': 'Participation in enrichment and extracurricular activities',
    # Behaviors: Self-Management Skills
    'B-SMS 1': 'Responsibility for self and actions',
    'B-SMS 2': 'Self-discipline and self-control',
    'B-SMS 3': 'Independent work',
    'B-SMS 4': 'Delayed gratification for long-term rewards',
    'B-SMS 5': 'Perseverance to achieve long- and short-term goals',
    'B-SMS 6': 'Ability to identify and overcome barriers',
    'B-SMS 7': 'Effective coping skills',
    'B-SMS 8': 'Balance of school, home and community activities',
    'B-SMS 9': 'Personal safety skills',
    'B-SMS 10': 'Ability to manage transitions and adapt to change',
    # Behaviors: Social Skills
    'B-SS 1': 'Effective oral and written communication skills and listening skills',
    'B-SS 2': 'Positive, respectful and supportive relationships with students who are similar to and different from them',
    'B-SS 3': 'Positive relationships with adults to support success',
    'B-SS 4': 'Empathy',
    'B-SS 5': 'Ethical decision-making and social responsibility',
    'B-SS 6': 'Effective collaboration and cooperation skills',
    'B-SS 7': 'Leadership and teamwork skills',
    'B-SS 8': 'Advocacy skills and ability to assert self, when necessary',
    'B-SS 9': 'Social maturity and behaviors appropriate to the situation and environment',
    'B-SS 10': 'Cultural awareness, sensitivity and responsiveness',
}

ASCA_DOMAINS = [
    ('academic', 'Academic Development'),
    ('career', 'Career Development'),
    ('social_emotional', 'Social/Emotional Development'),
]
ASCA_DOMAIN_KEYS = [k for k, _ in ASCA_DOMAINS]

# ---------------------------------------------------------------------------
# 2. Pathways (existing CollegeCareerPlan.PATHWAYS keys) + 'all'
# ---------------------------------------------------------------------------

PATHWAYS = ['undecided', '4year', '2year', 'cte_trade', 'military', 'workforce']
PATHWAY_KEYS = PATHWAYS + ['all']

COLLEGE_BOUND = ['undecided', '4year', '2year', 'cte_trade']  # anyone who might file aid forms

# Plan fields a checklist item may update automatically when checked.
PLAN_FIELD_TARGETS = [
    ('fafsa_status', 'submitted'),
    ('dream_act_status', 'submitted'),
    ('css_profile_status', 'submitted'),
    ('personal_statement_status', 'final'),
    ('transcript_sent', True),
]

SEASONS = ['fall', 'winter', 'spring', 'any']

FRAMEWORK_TAGS = [
    'SFBT:scaling', 'SFBT:exception', 'SFBT:miracle', 'SFBT:coping',
    'SFBT:relationship', 'SFBT:compliment', 'SFBT:goal', 'SFBT:whats_better',
    'SFBT:next_step', 'ASCA',
]

# ---------------------------------------------------------------------------
# 6. Ordering for the UI
# ---------------------------------------------------------------------------

CHECKLIST_GROUPS = [
    ('plan', 'The Plan'),
    ('applications', 'Applications'),
    ('financial_aid', 'Paying for It'),
    ('testing_records', 'Tests & Records'),
    ('after_acceptance', 'After You Get In'),
    ('workforce_military', 'Work & Military'),
    ('wellbeing', 'Taking Care of You'),
]
CHECKLIST_GROUP_KEYS = [k for k, _ in CHECKLIST_GROUPS]

SECTIONS = [
    ('opening', 'Opening', 'Check in as a person first, then set the goal for today.'),
    ('followup_visit', 'Since Last Time', "Follow-up visits start here: what's better, and how did last time's step go?"),
    ('scaling', 'Scaling', 'Where are they on a 0-10 today, and what already got them there?'),
    ('strengths_exceptions', 'Strengths & Exceptions', 'Find the times it already worked and the skills that made it work.'),
    ('goals_future', 'Goals & the Future', 'Miracle question, the year-from-now picture, and Plan B.'),
    ('barriers_coping', 'Barriers & Coping', "Name what's in the way, and how they've kept going anyway."),
    ('support_relationships', 'Support & People', 'Who is in their corner, and who would notice progress first.'),
    ('next_step', 'Next Step', 'One small, student-owned step with a date.'),
    ('closing', 'Closing', 'A specific compliment, one takeaway, and the next meeting on the calendar.'),
]
SECTION_KEYS = [k for k, _, _ in SECTIONS]

# ---------------------------------------------------------------------------
# 5. DEADLINE_DEFAULTS - California seniors, 2026-27 (ordered by date)
# ---------------------------------------------------------------------------

DEADLINE_DEFAULTS = [
    {
        'key': 'fafsa_open', 'label': '2027-28 FAFSA opens', 'date': '2026-10-01',
        'pathways': COLLEGE_BOUND, 'category': 'financial_aid',
        'source': 'Federal Student Aid (U.S. Department of Education)', 'verify': True,
        'note': 'Opening dates have shifted in recent years (Dec 2023, then phased Oct/Nov launches) - confirm the actual go-live date before the fall push.',
    },
    {
        'key': 'cadaa_open', 'label': '2027-28 California Dream Act Application opens', 'date': '2026-10-01',
        'pathways': COLLEGE_BOUND, 'category': 'financial_aid',
        'source': 'California Student Aid Commission (CSAC)', 'verify': True,
        'note': 'For undocumented, DACA, TPS and U-visa students who cannot file the FAFSA; usually opens the same day as the FAFSA.',
    },
    {
        'key': 'css_profile_open', 'label': 'CSS Profile opens (deadlines vary by college)', 'date': '2026-10-01',
        'pathways': ['4year'], 'category': 'financial_aid',
        'source': 'College Board', 'verify': True,
        'note': 'Only some private colleges require it; each sets its own deadline (often mid-November for early plans, January-February for regular).',
    },
    {
        'key': 'uc_csu_app_window_open', 'label': 'UC and CSU application submission window opens', 'date': '2026-10-01',
        'pathways': ['4year', 'undecided'], 'category': 'application',
        'source': "UC Office of the President / CSU Chancellor's Office", 'verify': False,
        'note': 'The UC form can be started August 1 but submitted only October 1-November 30; Cal State Apply opens October 1.',
    },
    {
        'key': 'cal_grant_gpa_upload', 'label': 'Cal Grant GPA verification uploaded by school', 'date': '2026-10-01',
        'pathways': COLLEGE_BOUND, 'category': 'records',
        'source': 'CSAC (high school submits electronically)', 'verify': True,
        'note': 'The school, not the student, submits GPAs; students should confirm in WebGrants 4 Students that theirs is on file.',
    },
    {
        'key': 'sat_oct', 'label': 'SAT - October test date', 'date': '2026-10-03',
        'pathways': ['4year', 'undecided'], 'category': 'testing',
        'source': 'College Board', 'verify': True,
        'note': 'Typically the first Saturday of October; registration closes about four weeks earlier. UC and CSU do not use scores.',
    },
    {
        'key': 'act_oct', 'label': 'ACT - October test date', 'date': '2026-10-24',
        'pathways': ['4year', 'undecided'], 'category': 'testing',
        'source': 'ACT, Inc.', 'verify': True,
        'note': 'Approximate; ACT publishes the national schedule each summer.',
    },
    {
        'key': 'early_decision_action', 'label': 'Early Decision / Early Action deadlines (most private colleges)', 'date': '2026-11-01',
        'pathways': ['4year'], 'category': 'application',
        'source': 'Each college', 'verify': True,
        'note': 'Common date but not universal (some use November 15); Early Decision is binding, Early Action is not.',
    },
    {
        'key': 'sat_nov', 'label': 'SAT - November test date', 'date': '2026-11-07',
        'pathways': ['4year', 'undecided'], 'category': 'testing',
        'source': 'College Board', 'verify': True,
        'note': 'Typically the first Saturday of November.',
    },
    {
        'key': 'uc_app_deadline', 'label': 'UC application deadline', 'date': '2026-11-30',
        'pathways': ['4year', 'undecided'], 'category': 'application',
        'source': 'UC Office of the President', 'verify': False,
        'note': 'One application covers all nine undergraduate campuses; the fee waiver covers up to four campuses. Closes 11:59 p.m. PT.',
    },
    {
        'key': 'csu_app_deadline', 'label': 'CSU application deadline (Cal State Apply)', 'date': '2026-11-30',
        'pathways': ['4year', 'undecided'], 'category': 'application',
        'source': "CSU Chancellor's Office", 'verify': False,
        'note': 'Impacted campuses and majors close on this date; a few non-impacted campuses keep accepting later, but do not count on it.',
    },
    {
        'key': 'csu_eop_app', 'label': 'CSU Educational Opportunity Program (EOP) application', 'date': '2026-11-30',
        'pathways': ['4year', 'undecided'], 'category': 'application',
        'source': 'Each CSU campus (inside Cal State Apply)', 'verify': True,
        'note': 'EOP is applied for within Cal State Apply and needs recommendation forms; some campuses set their own EOP deadline, so check each one.',
    },
    {
        'key': 'sat_dec', 'label': 'SAT - December test date', 'date': '2026-12-05',
        'pathways': ['4year', 'undecided'], 'category': 'testing',
        'source': 'College Board', 'verify': True,
        'note': 'Typically the first Saturday of December; last date most colleges accept for regular decision.',
    },
    {
        'key': 'act_dec', 'label': 'ACT - December test date', 'date': '2026-12-12',
        'pathways': ['4year', 'undecided'], 'category': 'testing',
        'source': 'ACT, Inc.', 'verify': True,
        'note': 'Approximate; confirm against the published ACT schedule.',
    },
    {
        'key': 'common_app_regular', 'label': 'Common App regular decision deadlines begin', 'date': '2027-01-01',
        'pathways': ['4year'], 'category': 'application',
        'source': 'Each college (via Common App)', 'verify': True,
        'note': 'Most private and out-of-state deadlines fall January 1-15; a few are February 1. Check every school on the list.',
    },
    {
        'key': 'asvab_target', 'label': 'ASVAB taken (rolling - suggested target)', 'date': '2027-01-15',
        'pathways': ['military', 'undecided'], 'category': 'testing',
        'source': 'U.S. Department of Defense (MEPCOM) / recruiter', 'verify': True,
        'note': 'No fixed deadline; this target leaves time for a retake (allowed after 30 days) before spring enlistment paperwork.',
    },
    {
        'key': 'local_scholarships', 'label': 'Local scholarship application packet due', 'date': '2027-03-01',
        'pathways': COLLEGE_BOUND, 'category': 'financial_aid',
        'source': 'Your school / district', 'verify': True,
        'note': 'Placeholder - replace with the date your school sets for its community scholarship packet.',
    },
    {
        'key': 'cal_grant_priority', 'label': 'Cal Grant priority deadline (FAFSA or CADAA + GPA on file)', 'date': '2027-03-02',
        'pathways': COLLEGE_BOUND, 'category': 'financial_aid',
        'source': 'CSAC', 'verify': False,
        'note': 'Set in state law (March 2); also the CSU and UC priority filing date for campus-based aid.',
    },
    {
        'key': 'middle_class_scholarship', 'label': 'Middle Class Scholarship consideration (automatic with FAFSA/CADAA by March 2)', 'date': '2027-03-02',
        'pathways': ['4year', '2year', 'undecided'], 'category': 'financial_aid',
        'source': 'CSAC', 'verify': False,
        'note': 'No separate application - UC, CSU and community college bachelor\'s-program students who file by March 2 are considered automatically.',
    },
    {
        'key': 'uc_decisions_released', 'label': 'UC admission decisions released (by end of March)', 'date': '2027-03-31',
        'pathways': ['4year'], 'category': 'decision',
        'source': 'Each UC campus', 'verify': True,
        'note': 'Campuses release between roughly March 1 and March 31; CSU decisions roll out February through April.',
    },
    {
        'key': 'cc_priority_registration', 'label': 'Community college priority registration for Fall 2027', 'date': '2027-04-15',
        'pathways': ['2year', 'undecided'], 'category': 'application',
        'source': 'Each community college', 'verify': True,
        'note': 'Varies by college (typically April-June); requires CCCApply, orientation, placement and an ed plan to be done first.',
    },
    {
        'key': 'sir_deadline', 'label': 'UC/CSU Statement of Intent to Register (SIR) due', 'date': '2027-05-01',
        'pathways': ['4year'], 'category': 'decision',
        'source': "UC Office of the President / CSU Chancellor's Office", 'verify': False,
        'note': 'Commit to one campus and pay (or defer) the deposit; waitlist offers can continue after this date.',
    },
    {
        'key': 'national_decision_day', 'label': 'National College Decision Day', 'date': '2027-05-01',
        'pathways': ['4year', '2year', 'cte_trade'], 'category': 'decision',
        'source': 'Colleges nationally', 'verify': False,
        'note': 'Most four-year colleges expect a deposit by this date; community colleges and many trade programs stay open later.',
    },
    {
        'key': 'ap_exams', 'label': 'AP exams (first two weeks of May)', 'date': '2027-05-03',
        'pathways': ['4year', '2year', 'undecided'], 'category': 'testing',
        'source': 'College Board', 'verify': True,
        'note': 'Approximate start; the exact two-week window is published each fall. Scores release in July.',
    },
    {
        'key': 'graduation', 'label': 'Graduation ceremony', 'date': '2027-06-04',
        'pathways': ['all'], 'category': 'other',
        'source': 'Your school / district', 'verify': True,
        'note': 'Placeholder - replace with your school\'s date; senior survey, fee clearance and cap & gown items key off this.',
    },
    {
        'key': 'final_transcript', 'label': 'Final transcript sent to your college or program', 'date': '2027-06-30',
        'pathways': ['4year', '2year', 'cte_trade'], 'category': 'records',
        'source': 'Each college (UC by July 1; CSU by July 15)', 'verify': True,
        'note': 'The registrar sends it after grades post; missing this can cancel a UC/CSU admission.',
    },
    {
        'key': 'cal_grant_cc_deadline', 'label': 'Cal Grant second deadline for community college students', 'date': '2027-09-02',
        'pathways': ['2year', 'undecided'], 'category': 'financial_aid',
        'source': 'CSAC', 'verify': False,
        'note': 'A safety net only for students attending a community college in fall who missed March 2; awards are limited.',
    },
]

DEADLINE_KEYS = [d['key'] for d in DEADLINE_DEFAULTS]

# ---------------------------------------------------------------------------
# 3. CHECKLIST
# ---------------------------------------------------------------------------

CHECKLIST = [
    # --- plan -------------------------------------------------------------
    {
        'key': 'pathway_chosen', 'label': 'Choose a main pathway', 'group': 'plan',
        'pathways': ['all'], 'maps_to': None, 'deadline_key': None, 'season': 'fall',
        'help': "Pick the direction you're leaning right now - four-year, community college, a trade program, the military, or straight to work - knowing you can change it as you learn more.",
    },
    {
        'key': 'backup_plan', 'label': 'Name a backup plan', 'group': 'plan',
        'pathways': ['all'], 'maps_to': None, 'deadline_key': None, 'season': 'fall',
        'help': "A Plan B isn't doubting yourself - it's making sure a rejection, a bad award letter, or a change of heart can't leave you with nothing in June.",
    },
    {
        'key': 'college_list', 'label': 'Build a college list (reach, match, safety)', 'group': 'plan',
        'pathways': ['4year', 'undecided'], 'maps_to': None, 'deadline_key': None, 'season': 'fall',
        'help': "Aim for six to ten schools: a couple you'd be lucky to get into, several where your grades fit, and at least two you're confident about and would actually attend.",
    },
    {
        'key': 'brag_sheet', 'label': 'Complete senior brag sheet', 'group': 'plan',
        'pathways': ['4year', '2year', 'cte_trade', 'undecided'], 'maps_to': None, 'deadline_key': None, 'season': 'fall',
        'help': "The brag sheet is where you list jobs, activities, family responsibilities and proud moments so I and your recommenders can write about the real you.",
    },
    {
        'key': 'career_interest_named', 'label': 'Name a career field to explore', 'group': 'plan',
        'pathways': ['undecided', 'workforce', 'cte_trade', '2year'], 'maps_to': None, 'deadline_key': None, 'season': 'fall',
        'help': "You don't need a life plan - just one field you're curious enough about to look into this semester.",
    },

    # --- applications -----------------------------------------------------
    {
        'key': 'uc_application', 'label': 'Submit UC application (Oct 1-Nov 30)', 'group': 'applications',
        'pathways': ['4year', 'undecided'], 'maps_to': None, 'deadline_key': 'uc_app_deadline', 'season': 'fall',
        'help': "One application covers all nine UC campuses, the fee waiver covers up to four, and it must be submitted between October 1 and November 30.",
    },
    {
        'key': 'csu_application', 'label': 'Submit CSU application on Cal State Apply (Oct 1-Nov 30)', 'group': 'applications',
        'pathways': ['4year', 'undecided'], 'maps_to': None, 'deadline_key': 'csu_app_deadline', 'season': 'fall',
        'help': "Cal State Apply opens October 1 and closes November 30; some campuses and majors are 'impacted' and fill up, so don't wait until the last week.",
    },
    {
        'key': 'csu_eop', 'label': 'Apply to EOP inside Cal State Apply (if eligible)', 'group': 'applications',
        'pathways': ['4year', 'undecided'], 'maps_to': None, 'deadline_key': 'csu_eop_app', 'season': 'fall',
        'help': "EOP is a CSU program for first-generation and lower-income students that adds advising, a summer bridge, and sometimes grant money - you apply in the same form and it needs two recommendations.",
    },
    {
        'key': 'early_apps', 'label': 'Submit Early Action / Early Decision applications', 'group': 'applications',
        'pathways': ['4year'], 'maps_to': None, 'deadline_key': 'early_decision_action', 'season': 'fall',
        'help': "Early Action lets you hear back sooner with no commitment; Early Decision is binding, so only use it if that school is your clear first choice and the cost works for your family.",
    },
    {
        'key': 'common_app_private', 'label': 'Submit Common App / private and out-of-state applications', 'group': 'applications',
        'pathways': ['4year'], 'maps_to': None, 'deadline_key': 'common_app_regular', 'season': 'winter',
        'help': "Most private and out-of-state colleges use the Common App, and each one sets its own deadline - write them all in one place.",
    },
    {
        'key': 'personal_statement_drafted', 'label': 'Draft personal statement / UC PIQs', 'group': 'applications',
        'pathways': ['4year', 'undecided'], 'maps_to': None, 'deadline_key': None, 'season': 'fall',
        'help': "UC asks for four Personal Insight Questions (350 words each), CSU has no essay, and the Common App essay is up to 650 words - start with the story only you can tell.",
    },
    {
        'key': 'personal_statement_final', 'label': 'Finalize personal statement / PIQs after review', 'group': 'applications',
        'pathways': ['4year', 'undecided'], 'maps_to': ('personal_statement_status', 'final'), 'deadline_key': 'uc_app_deadline', 'season': 'fall',
        'help': "Have one trusted adult read it, fix what's unclear, keep your own voice, and then stop - done is better than perfect.",
    },
    {
        'key': 'rec_letters_requested', 'label': 'Request letters of recommendation', 'group': 'applications',
        'pathways': ['4year', 'undecided'], 'maps_to': None, 'deadline_key': None, 'season': 'fall',
        'help': "UC and CSU don't take letters, but private colleges, EOP and scholarships do - ask in person, give at least three weeks, and share your brag sheet.",
    },
    {
        'key': 'rec_letters_received', 'label': 'Confirm letters were submitted', 'group': 'applications',
        'pathways': ['4year', 'undecided'], 'maps_to': None, 'deadline_key': None, 'season': 'winter',
        'help': "Check each application portal to confirm the letter shows as received, and send a friendly reminder a week before the deadline if it doesn't.",
    },
    {
        'key': 'rec_letters_thank_you', 'label': 'Thank your recommenders', 'group': 'applications',
        'pathways': ['4year', 'undecided'], 'maps_to': None, 'deadline_key': None, 'season': 'winter',
        'help': "A short note or email means a lot to the adults who wrote for you - and tell them where you got in.",
    },
    {
        'key': 'cccapply_submitted', 'label': 'Submit CCCApply (community college application)', 'group': 'applications',
        'pathways': ['2year', 'undecided'], 'maps_to': None, 'deadline_key': None, 'season': 'winter',
        'help': "CCCApply is free, takes about 30 minutes, and you can apply any time - but doing it by winter gets you into orientation and priority registration sooner.",
    },
    {
        'key': 'cc_orientation_assessment_edplan', 'label': 'Complete orientation, placement and ed plan', 'group': 'applications',
        'pathways': ['2year', 'undecided'], 'maps_to': None, 'deadline_key': 'cc_priority_registration', 'season': 'spring',
        'help': "Finish online orientation, the English and math self-placement, and a first-semester ed plan with a college counselor - these three steps unlock priority registration.",
    },
    {
        'key': 'cc_priority_registration', 'label': 'Register for classes during priority registration', 'group': 'applications',
        'pathways': ['2year', 'undecided'], 'maps_to': None, 'deadline_key': 'cc_priority_registration', 'season': 'spring',
        'help': "Register the day your window opens - popular classes fill fast, and a full schedule keeps your financial aid intact.",
    },
    {
        'key': 'cc_promise', 'label': 'Apply for California College Promise / Promise Grant', 'group': 'applications',
        'pathways': ['2year', 'undecided'], 'maps_to': None, 'deadline_key': None, 'season': 'spring',
        'help': "The California College Promise Grant waives enrollment fees, and most colleges also have a Promise program covering your first two years - both start with your FAFSA or Dream Act application.",
    },
    {
        'key': 'cte_program_application', 'label': 'Apply to CTE / trade program', 'group': 'applications',
        'pathways': ['cte_trade', 'undecided'], 'maps_to': None, 'deadline_key': None, 'season': 'winter',
        'help': "Trade and CTE programs each have their own application, start dates and sometimes a waitlist - apply early, and ask for the total cost and whether it's accredited so financial aid can apply.",
    },

    # --- financial_aid ----------------------------------------------------
    {
        'key': 'fsa_ids_created', 'label': 'Create FSA IDs (student and parent)', 'group': 'financial_aid',
        'pathways': COLLEGE_BOUND, 'maps_to': None, 'deadline_key': 'fafsa_open', 'season': 'fall',
        'help': "You and a parent each need your own FSA ID at StudentAid.gov (a parent without a Social Security number can still make one) - if you'll file the Dream Act application instead, you can skip this.",
    },
    {
        'key': 'fafsa_submitted', 'label': 'Submit the FAFSA', 'group': 'financial_aid',
        'pathways': COLLEGE_BOUND, 'maps_to': ('fafsa_status', 'submitted'), 'deadline_key': 'cal_grant_priority', 'season': 'fall',
        'help': "The FAFSA is free, opens in the fall, and must be in by March 2 for Cal Grant - list every college you might attend, and answer quickly if a college asks for 'verification' documents later.",
    },
    {
        'key': 'cadaa_submitted', 'label': 'Submit the California Dream Act Application (CADAA)', 'group': 'financial_aid',
        'pathways': COLLEGE_BOUND, 'maps_to': ('dream_act_status', 'submitted'), 'deadline_key': 'cal_grant_priority', 'season': 'fall',
        'help': "If you're undocumented, have DACA, TPS or a U visa, file the Dream Act application instead of the FAFSA - it's confidential, not shared with immigration, and unlocks Cal Grant, Promise and UC/CSU aid.",
    },
    {
        'key': 'cal_grant_gpa_confirmed', 'label': 'Confirm Cal Grant GPA is on file', 'group': 'financial_aid',
        'pathways': COLLEGE_BOUND, 'maps_to': None, 'deadline_key': 'cal_grant_gpa_upload', 'season': 'fall',
        'help': "Your school sends your GPA to the state (CSAC) - make a free WebGrants 4 Students account to check it's there, because no GPA means no Cal Grant.",
    },
    {
        'key': 'css_profile_submitted', 'label': 'Submit CSS Profile (if a college requires it)', 'group': 'financial_aid',
        'pathways': ['4year'], 'maps_to': ('css_profile_status', 'submitted'), 'deadline_key': None, 'season': 'fall',
        'help': "Only some private colleges want the CSS Profile; it has a fee, but fee waivers are automatic for lower-income families, and each college sets its own deadline.",
    },
    {
        'key': 'scholarship_search_started', 'label': 'Start a scholarship search and tracker', 'group': 'financial_aid',
        'pathways': COLLEGE_BOUND, 'maps_to': None, 'deadline_key': None, 'season': 'fall',
        'help': "Make a free profile on one or two scholarship sites, ask me for our school's list, and track deadlines in one place - an hour a week here can pay better than a part-time job.",
    },
    {
        'key': 'scholarship_apps_submitted', 'label': 'Submit at least 3 scholarship applications', 'group': 'financial_aid',
        'pathways': COLLEGE_BOUND, 'maps_to': None, 'deadline_key': None, 'season': 'winter',
        'help': "Aim for at least three - smaller and local scholarships have fewer applicants, and one good essay can be reused for many.",
    },
    {
        'key': 'local_scholarships_applied', 'label': 'Apply for local scholarships', 'group': 'financial_aid',
        'pathways': COLLEGE_BOUND, 'maps_to': None, 'deadline_key': 'local_scholarships', 'season': 'winter',
        'help': "Our local scholarship packet is usually one application for many awards from community groups - ask me when it opens.",
    },
    {
        'key': 'mcs_checked', 'label': 'Confirm Middle Class Scholarship consideration', 'group': 'financial_aid',
        'pathways': ['4year', '2year', 'undecided'], 'maps_to': None, 'deadline_key': 'middle_class_scholarship', 'season': 'spring',
        'help': "If you're headed to a UC or CSU and filed your FAFSA or Dream Act application by March 2, you're automatically considered for the Middle Class Scholarship - just watch for it on your award letter.",
    },
    {
        'key': 'aid_offers_compared', 'label': 'Compare financial aid award letters', 'group': 'financial_aid',
        'pathways': ['4year', '2year', 'cte_trade'], 'maps_to': None, 'deadline_key': 'national_decision_day', 'season': 'spring',
        'help': "Line up each offer by what you'd actually pay after free money (grants and scholarships), not the sticker price - loans and work-study are not free.",
    },
    {
        'key': 'aid_verification_done', 'label': 'Respond to any financial aid verification request', 'group': 'financial_aid',
        'pathways': COLLEGE_BOUND, 'maps_to': None, 'deadline_key': None, 'season': 'spring',
        'help': "Some students are picked for 'verification' and asked for tax documents - it's routine, not an accusation, but your aid won't pay out until it's done.",
    },

    # --- testing_records --------------------------------------------------
    {
        'key': 'sat_act_decision', 'label': 'Decide whether to take or send SAT/ACT', 'group': 'testing_records',
        'pathways': ['4year', 'undecided'], 'maps_to': None, 'deadline_key': 'sat_oct', 'season': 'fall',
        'help': "UC and CSU don't use SAT or ACT scores for admission (a high ACT English score can still clear UC's writing requirement, and both use scores for course placement), and most other colleges are test-optional - take it only if it helps you somewhere specific, and send scores only where they help.",
    },
    {
        'key': 'ap_ib_scores_sent', 'label': 'Send AP / IB scores to your college', 'group': 'testing_records',
        'pathways': ['4year', '2year', 'undecided'], 'maps_to': None, 'deadline_key': None, 'season': 'spring',
        'help': "After you commit, send AP scores through College Board (IB through your coordinator) - many colleges give credit for a 3 or higher, and one free score send is included each year.",
    },
    {
        'key': 'transcript_midyear_sent', 'label': 'Request mid-year transcript (if a college asks)', 'group': 'testing_records',
        'pathways': ['4year'], 'maps_to': None, 'deadline_key': None, 'season': 'winter',
        'help': "Some private colleges want first-semester senior grades - request it from the registrar in January if any school on your list asks.",
    },
    {
        'key': 'transcript_final_sent', 'label': 'Request final transcript sent', 'group': 'testing_records',
        'pathways': ['4year', '2year', 'cte_trade', 'undecided'], 'maps_to': ('transcript_sent', True), 'deadline_key': 'final_transcript', 'season': 'spring',
        'help': "After graduation, have the registrar send your final transcript to the one place you're going - UC wants it by July 1, CSU by July 15, and community colleges before you register.",
    },
    {
        'key': 'health_records_gathered', 'label': 'Gather immunization / health records', 'group': 'testing_records',
        'pathways': ['all'], 'maps_to': None, 'deadline_key': None, 'season': 'spring',
        'help': "Colleges, the military and some jobs ask for immunization records (often MMR, Tdap, meningitis, hepatitis B and a TB screen) - get a copy from your doctor or the school office now while it's easy.",
    },

    # --- after_acceptance -------------------------------------------------
    {
        'key': 'offers_compared', 'label': 'Compare admission offers', 'group': 'after_acceptance',
        'pathways': ['4year', '2year', 'cte_trade'], 'maps_to': None, 'deadline_key': 'national_decision_day', 'season': 'spring',
        'help': "Look at four things: real cost, whether your major or program is there, how far it is from the people who keep you steady, and what help they give first-year students.",
    },
    {
        'key': 'sir_submitted', 'label': 'Submit SIR / deposit by May 1 and decline the others', 'group': 'after_acceptance',
        'pathways': ['4year'], 'maps_to': None, 'deadline_key': 'sir_deadline', 'season': 'spring',
        'help': "Say yes to one college by May 1 (UC and CSU call it the Statement of Intent to Register), pay the deposit or ask for a deferral if money is tight, and politely decline the others so waitlisted students can move up.",
    },
    {
        'key': 'housing_applied', 'label': 'Apply for housing', 'group': 'after_acceptance',
        'pathways': ['4year'], 'maps_to': None, 'deadline_key': None, 'season': 'spring',
        'help': "Housing applications and deposits often open before May 1 and fill up - apply as soon as you're leaning toward a school, even before you commit.",
    },
    {
        'key': 'orientation_and_placement', 'label': 'Sign up for orientation and finish placement steps', 'group': 'after_acceptance',
        'pathways': ['4year', '2year', 'cte_trade'], 'maps_to': None, 'deadline_key': None, 'season': 'spring',
        'help': "Register for orientation the day it opens, and check for placement steps (UC's Entry Level Writing Requirement and your campus's writing/math placement, a CSU's first-year placement steps, or a college's self-placement) - skipping them can block registration.",
    },
    {
        'key': 'summer_melt_checkin', 'label': 'Set up portal, email and a summer check-in', 'group': 'after_acceptance',
        'pathways': ['all'], 'maps_to': None, 'deadline_key': None, 'season': 'spring',
        'help': "Set up your college or program account now, check it weekly all summer, and pick who you'll text if something goes wrong in July - summer is where plans quietly fall apart.",
    },
    {
        'key': 'senior_survey_completed', 'label': 'Complete senior exit survey', 'group': 'after_acceptance',
        'pathways': ['all'], 'maps_to': None, 'deadline_key': 'graduation', 'season': 'spring',
        'help': "Tell us where you're headed - it helps the school support next year's seniors and closes out your file.",
    },
    {
        'key': 'graduation_checklist', 'label': 'Cap & gown, fees and graduation checklist', 'group': 'after_acceptance',
        'pathways': ['all'], 'maps_to': None, 'deadline_key': 'graduation', 'season': 'spring',
        'help': "Confirm you've cleared any fees, ordered your cap and gown, and know the ceremony date and ticket rules.",
    },

    # --- workforce_military -----------------------------------------------
    {
        'key': 'asvab_taken', 'label': 'Take the ASVAB', 'group': 'workforce_military',
        'pathways': ['military', 'undecided'], 'maps_to': None, 'deadline_key': 'asvab_target', 'season': 'fall',
        'help': "The ASVAB is free, takes about three hours, and your score decides which branches and jobs are open to you - practice tests are online and you can retake it after 30 days.",
    },
    {
        'key': 'recruiter_meeting', 'label': 'Meet with a recruiter (bring an adult)', 'group': 'workforce_military',
        'pathways': ['military'], 'maps_to': None, 'deadline_key': None, 'season': 'winter',
        'help': "Talk to recruiters from more than one branch, bring a parent or trusted adult, and get the job, any bonus and the education benefits in writing before you sign anything.",
    },
    {
        'key': 'parent_consent_military', 'label': 'Parent/guardian consent to enlist (if under 18)', 'group': 'workforce_military',
        'pathways': ['military'], 'maps_to': None, 'deadline_key': None, 'season': 'winter',
        'help': "If you're 17, a parent or guardian has to sign for you to enlist - and you can always talk it through with me first.",
    },
    {
        'key': 'meps_completed', 'label': 'Complete MEPS (physical, background, job selection)', 'group': 'workforce_military',
        'pathways': ['military'], 'maps_to': None, 'deadline_key': None, 'season': 'spring',
        'help': "MEPS is the medical exam, background check and job-selection day - it's long, so eat first, bring your ID and any medical records, and read the job and dates before you sign the contract.",
    },
    {
        'key': 'selective_service_registered', 'label': 'Register for Selective Service (turning 18)', 'group': 'workforce_military',
        'pathways': ['all'], 'maps_to': None, 'deadline_key': None, 'season': 'any',
        'help': "Most men 18 to 25, whatever their immigration status, must register within 30 days of turning 18 - it takes two minutes at sss.gov and is required for federal jobs, job-training programs and some state benefits.",
    },
    {
        'key': 'resume_done', 'label': 'Write a one-page resume', 'group': 'workforce_military',
        'pathways': ['workforce', 'cte_trade', 'military', 'undecided'], 'maps_to': None, 'deadline_key': None, 'season': 'fall',
        'help': "One page: contact info, education, work or volunteer experience, skills and any certifications - use a school template and have someone proofread it.",
    },
    {
        'key': 'references_lined_up', 'label': 'Line up 2-3 references', 'group': 'workforce_military',
        'pathways': ['workforce', 'cte_trade'], 'maps_to': None, 'deadline_key': None, 'season': 'winter',
        'help': "Ask two or three adults (a teacher, coach or manager) if you can list them, and give them a heads-up whenever you apply somewhere.",
    },
    {
        'key': 'work_permit_obtained', 'label': 'Get a work permit (if under 18)', 'group': 'workforce_military',
        'pathways': ['workforce', 'cte_trade', 'undecided'], 'maps_to': None, 'deadline_key': None, 'season': 'any',
        'help': "In California you need a work permit until you turn 18 or graduate - the form is in the school office and usually takes a day.",
    },
    {
        'key': 'apprenticeship_search', 'label': 'Explore apprenticeships and job centers', 'group': 'workforce_military',
        'pathways': ['workforce', 'cte_trade', 'undecided'], 'maps_to': None, 'deadline_key': None, 'season': 'winter',
        'help': "Apprenticeships pay you while you learn a trade - search the state's apprenticeship finder (California DIR), ask about pre-apprenticeship programs, and visit the America's Job Center of California near you.",
    },
    {
        'key': 'job_applications_submitted', 'label': 'Apply to at least 3 jobs', 'group': 'workforce_military',
        'pathways': ['workforce'], 'maps_to': None, 'deadline_key': None, 'season': 'spring',
        'help': "Apply to at least three places, follow up in person or by phone after a few days, and keep a list of where you applied and when.",
    },

    # --- wellbeing --------------------------------------------------------
    {
        'key': 'support_person_identified', 'label': 'Name your support people', 'group': 'wellbeing',
        'pathways': ['all'], 'maps_to': None, 'deadline_key': None, 'season': 'any',
        'help': "Name one adult and one friend you can go to when this gets hard - and write their names in your plan so you don't have to think about it in the moment.",
    },
    {
        'key': 'stress_plan', 'label': 'Make a plan for stress and heavy weeks', 'group': 'wellbeing',
        'pathways': ['all'], 'maps_to': None, 'deadline_key': None, 'season': 'winter',
        'help': "Pick two things that actually help you reset, decide when you'll use them in deadline weeks, and know one place to call or text if things get heavy (the wellness center or 988 - you don't have to be in crisis to use them).",
    },
    {
        'key': 'transition_plan', 'label': 'Write a transition plan for after June', 'group': 'wellbeing',
        'pathways': ['all'], 'maps_to': None, 'deadline_key': None, 'season': 'spring',
        'help': "Write down what changes after graduation - where you'll live, how you'll get around, how you'll pay for things, and who you'll check in with - so the surprises are smaller.",
    },
]

CHECKLIST_KEYS = [c['key'] for c in CHECKLIST]

# ---------------------------------------------------------------------------
# 4. QUESTIONS (Solution-Focused Brief Therapy + ASCA)
# ---------------------------------------------------------------------------

QUESTIONS = [
    # --- opening ----------------------------------------------------------
    {
        'key': 'open_how_are_you', 'section': 'opening',
        'text': "Before we talk about plans - how are you doing today, really?",
        'framework': ['ASCA'], 'asca': ['M 1'], 'domain': 'social_emotional',
        'answer_type': 'text', 'when': 'any', 'pathways': ['all'],
        'coach': "Let the silence sit; if something big comes up, follow it before anything on the checklist.",
    },
    {
        'key': 'open_best_hopes', 'section': 'opening',
        'text': "What are your best hopes for our time today? What would make this meeting worth it for you?",
        'framework': ['SFBT:goal'], 'asca': ['B-LS 7'], 'domain': 'career',
        'answer_type': 'text', 'when': 'any', 'pathways': ['all'],
        'coach': "Write their goal in their words at the top of the note; return to it at the close.",
    },
    {
        'key': 'open_where_you_are', 'section': 'opening',
        'text': "In your own words, where are you at with your plan for after graduation right now?",
        'framework': ['ASCA'], 'asca': ['M 6', 'B-LS 7'], 'domain': 'career',
        'answer_type': 'text', 'when': 'first', 'pathways': ['all'],
        'coach': "Listen for the pathway and the backup plan; don't correct anything yet, just record what they believe.",
    },
    {
        'key': 'open_going_well', 'section': 'opening',
        'text': "What's one thing about senior year that's going well so far?",
        'framework': ['SFBT:exception', 'SFBT:compliment'], 'asca': ['M 3', 'M 4'], 'domain': 'social_emotional',
        'answer_type': 'text', 'when': 'first', 'pathways': ['all'],
        'coach': "Whatever they name, ask how they made that happen - it's the first strength you'll use later.",
    },

    # --- followup_visit ---------------------------------------------------
    {
        'key': 'fu_whats_better', 'section': 'followup_visit',
        'text': "What's better since we last met - even a little?",
        'framework': ['SFBT:whats_better'], 'asca': ['M 4', 'B-SMS 5'], 'domain': 'social_emotional',
        'answer_type': 'text', 'when': 'followup', 'pathways': ['all'],
        'coach': "If they say 'nothing', ask 'What's stayed the same instead of getting worse?' and how they managed that.",
    },
    {
        'key': 'fu_how_did_you', 'section': 'followup_visit',
        'text': "How did you make that happen?",
        'framework': ['SFBT:whats_better', 'SFBT:compliment'], 'asca': ['B-SMS 1', 'M 4'], 'domain': 'social_emotional',
        'answer_type': 'text', 'when': 'followup', 'pathways': ['all'],
        'coach': "Give the credit to them, specifically - name the action, not the trait.",
    },
    {
        'key': 'fu_step_status', 'section': 'followup_visit',
        'text': "Last time you said you'd [step] by [date]. How did it go?",
        'framework': ['SFBT:next_step'], 'asca': ['B-SMS 1', 'B-LS 7'], 'domain': 'academic',
        'answer_type': 'text', 'when': 'followup', 'pathways': ['all'],
        'coach': "If it didn't happen, no lecture - ask what part did happen and what got in the way, then shrink the step.",
    },
    {
        'key': 'fu_scale_again', 'section': 'followup_visit',
        'text': "Same 0-to-10 scale as last time, where 10 is 'my plan is handled' - where are you today? What moved it?",
        'framework': ['SFBT:scaling', 'SFBT:whats_better'], 'asca': ['M 4', 'B-SMS 5'], 'domain': 'career',
        'answer_type': 'scale', 'when': 'followup', 'pathways': ['all'],
        'coach': "Compare to the last recorded number out loud; a drop is information, not failure - ask what would bring it back.",
    },
    {
        'key': 'fu_keep_doing', 'section': 'followup_visit',
        'text': "What do you want to keep doing that's working?",
        'framework': ['SFBT:whats_better'], 'asca': ['B-LS 4', 'B-SMS 2'], 'domain': 'academic',
        'answer_type': 'text', 'when': 'followup', 'pathways': ['all'],
        'coach': "Make sure it lands in the plan as a habit, not just a note.",
    },
    {
        'key': 'fu_next_30_days', 'section': 'followup_visit',
        'text': "Let's look at what's due in the next 30 days. Which of these feel handled, and which are you not sure about?",
        'framework': ['ASCA'], 'asca': ['B-LS 3', 'B-SMS 1'], 'domain': 'academic',
        'answer_type': 'text', 'when': 'followup', 'pathways': ['all'],
        'coach': "Pull up the deadline list and go item by item; 'not sure' is where the next step lives.",
    },

    # --- scaling ----------------------------------------------------------
    {
        'key': 'scale_plan_progress', 'section': 'scaling',
        'text': "On a scale of 0 to 10, where 10 means your plan for after high school is completely handled and 0 means you haven't started, where are you today?",
        'framework': ['SFBT:scaling'], 'asca': ['M 4', 'B-SMS 5'], 'domain': 'career',
        'answer_type': 'scale', 'when': 'first', 'pathways': ['all'],
        'coach': "Accept the number without arguing; every follow-up question uses it.",
    },
    {
        'key': 'scale_why_not_lower', 'section': 'scaling',
        'text': "What makes it a [number] and not two points lower? What have you already done?",
        'framework': ['SFBT:scaling', 'SFBT:compliment'], 'asca': ['M 4', 'B-SMS 1'], 'domain': 'career',
        'answer_type': 'text', 'when': 'any', 'pathways': ['all'],
        'coach': "Write down every concrete thing they list - those are strengths and proof of progress.",
    },
    {
        'key': 'scale_one_higher', 'section': 'scaling',
        'text': "What would a [number + 1] look like? What would be different that you or someone else would notice?",
        'framework': ['SFBT:scaling', 'SFBT:goal'], 'asca': ['B-LS 7'], 'domain': 'career',
        'answer_type': 'text', 'when': 'any', 'pathways': ['all'],
        'coach': "Push for something visible and small; 'I'd feel better' becomes 'I'd have my FSA ID made'.",
    },
    {
        'key': 'scale_one_thing_up', 'section': 'scaling',
        'text': "What's one small thing that would move you up just one point?",
        'framework': ['SFBT:scaling', 'SFBT:next_step'], 'asca': ['B-SMS 5', 'B-LS 7'], 'domain': 'career',
        'answer_type': 'text', 'when': 'any', 'pathways': ['all'],
        'coach': "This is often the next step - carry it forward to the Next Step section.",
    },
    {
        'key': 'scale_stress', 'section': 'scaling',
        'text': "Different scale: 0 to 10, how much is all of this weighing on you right now, where 10 is the most stressed you've ever been?",
        'framework': ['SFBT:scaling'], 'asca': ['M 1', 'B-SMS 7'], 'domain': 'social_emotional',
        'answer_type': 'scale', 'when': 'any', 'pathways': ['all'],
        'coach': "At 7 or above, pause the checklist and move to the coping questions; consider a wellness referral and check safety if anything in their words concerns you.",
    },
    {
        'key': 'scale_others_view', 'section': 'scaling',
        'text': "If your parent, guardian or a teacher who knows you were rating you on that same 0-to-10 plan scale, what number would they give? What do they see?",
        'framework': ['SFBT:scaling', 'SFBT:relationship'], 'asca': ['B-SS 3', 'M 4'], 'domain': 'social_emotional',
        'answer_type': 'text', 'when': 'any', 'pathways': ['all'],
        'coach': "A gap between the two numbers is worth a gentle 'what do they know that you don't - or the other way around?'",
    },

    # --- strengths_exceptions ---------------------------------------------
    {
        'key': 'exc_hard_thing_done', 'section': 'strengths_exceptions',
        'text': "Tell me about a time you got something like this done even though it was hard - a big project, a job application, a tryout, anything.",
        'framework': ['SFBT:exception'], 'asca': ['B-SMS 5', 'B-SMS 6'], 'domain': 'academic',
        'answer_type': 'text', 'when': 'first', 'pathways': ['all'],
        'coach': "Stay with the story long enough to hear the steps they took, not just the outcome.",
    },
    {
        'key': 'exc_how_did_you', 'section': 'strengths_exceptions',
        'text': "How did you do that? What did you do first?",
        'framework': ['SFBT:exception'], 'asca': ['B-LS 3', 'B-SMS 3'], 'domain': 'academic',
        'answer_type': 'text', 'when': 'first', 'pathways': ['all'],
        'coach': "Reflect their method back in their own words: 'So you started small and asked one person for help.'",
    },
    {
        'key': 'exc_use_again', 'section': 'strengths_exceptions',
        'text': "Which part of that could you use again for this?",
        'framework': ['SFBT:exception', 'SFBT:next_step'], 'asca': ['B-LS 1', 'B-SMS 5'], 'domain': 'academic',
        'answer_type': 'text', 'when': 'any', 'pathways': ['all'],
        'coach': "Connect it directly to a checklist item so the strength has a job to do.",
    },
    {
        'key': 'str_proud', 'section': 'strengths_exceptions',
        'text': "What's something you've done in high school that you're proud of, even if nobody else noticed?",
        'framework': ['SFBT:compliment'], 'asca': ['M 4', 'M 5'], 'domain': 'social_emotional',
        'answer_type': 'text', 'when': 'first', 'pathways': ['all'],
        'coach': "Family responsibilities, jobs and showing up count - say so; it may also belong on the brag sheet or in an essay.",
    },
    {
        'key': 'str_others_say', 'section': 'strengths_exceptions',
        'text': "What would your favorite teacher or your best friend say you're good at?",
        'framework': ['SFBT:relationship', 'SFBT:compliment'], 'asca': ['B-SS 3', 'M 4'], 'domain': 'social_emotional',
        'answer_type': 'text', 'when': 'first', 'pathways': ['all'],
        'coach': "Students who can't compliment themselves can usually report what others see - use that to name a strength.",
    },

    # --- goals_future -----------------------------------------------------
    {
        'key': 'miracle_question', 'section': 'goals_future',
        'text': "Suppose tonight, while you're asleep, a miracle happens and your plan for after high school is completely handled - but you were asleep, so you don't know it happened. When you wake up tomorrow, what's the first small thing you'd notice that tells you it's handled?",
        'framework': ['SFBT:miracle'], 'asca': ['B-LS 7', 'M 6'], 'domain': 'career',
        'answer_type': 'text', 'when': 'first', 'pathways': ['all'],
        'coach': "Slow down and keep asking 'what else would you notice?' - you want details of a normal day, not a job title.",
    },
    {
        'key': 'miracle_who_notices', 'section': 'goals_future',
        'text': "Who else would notice something's different about you that morning? What would they see you doing?",
        'framework': ['SFBT:miracle', 'SFBT:relationship'], 'asca': ['B-SS 3', 'B-LS 7'], 'domain': 'social_emotional',
        'answer_type': 'text', 'when': 'first', 'pathways': ['all'],
        'coach': "The people they name are their support system; note them for the Support section.",
    },
    {
        'key': 'miracle_already_happening', 'section': 'goals_future',
        'text': "Are there already little pieces of that miracle happening now, even a bit?",
        'framework': ['SFBT:miracle', 'SFBT:exception'], 'asca': ['M 4', 'B-SMS 5'], 'domain': 'career',
        'answer_type': 'text', 'when': 'any', 'pathways': ['all'],
        'coach': "Tie each piece to something already checked off; the plan is further along than they feel.",
    },
    {
        'key': 'goal_one_year_out', 'section': 'goals_future',
        'text': "Picture yourself the fall after graduation, a few months after you walk. Where are you living, and what does a normal Tuesday look like?",
        'framework': ['SFBT:goal'], 'asca': ['B-LS 7', 'M 6'], 'domain': 'career',
        'answer_type': 'text', 'when': 'first', 'pathways': ['all'],
        'coach': "Work backward from that Tuesday to what has to be true by June - that's the checklist in their language.",
    },
    {
        'key': 'goal_why_it_matters', 'section': 'goals_future',
        'text': "Why does this path matter to you? What does it get you that you actually care about?",
        'framework': ['SFBT:goal'], 'asca': ['M 6', 'B-LS 9'], 'domain': 'career',
        'answer_type': 'text', 'when': 'any', 'pathways': ['all'],
        'coach': "If the answer is someone else's reason, gently ask what they'd choose if it were only up to them - then hold both.",
    },
    {
        'key': 'goal_backup', 'section': 'goals_future',
        'text': "If Plan A doesn't work out the way you hope, what's a Plan B you'd still feel OK about?",
        'framework': ['ASCA', 'SFBT:goal'], 'asca': ['B-SMS 10', 'B-LS 1'], 'domain': 'career',
        'answer_type': 'text', 'when': 'any', 'pathways': ['all'],
        'coach': "Frame Plan B as being ready for anything, not as doubt; record it in the plan so it's real.",
    },
    {
        'key': 'goal_undecided_explore', 'section': 'goals_future',
        'text': "You don't have to know your whole life today. What's one thing you'd like to try, visit or learn more about this year?",
        'framework': ['SFBT:goal'], 'asca': ['M 6', 'B-LS 10'], 'domain': 'career',
        'answer_type': 'text', 'when': 'any', 'pathways': ['undecided'],
        'coach': "Turn it into a step: a campus visit, a job shadow, a CTE class tour, or one conversation with someone in that field.",
    },
    {
        'key': 'goal_good_job', 'section': 'goals_future',
        'text': "What would a good job look like for you in the first year out - pay, hours, what you'd be learning, who you'd be around?",
        'framework': ['SFBT:goal'], 'asca': ['B-LS 7', 'B-LS 9'], 'domain': 'career',
        'answer_type': 'text', 'when': 'any', 'pathways': ['workforce', 'cte_trade'],
        'coach': "Compare their answer to real local postings and apprenticeship pay so the picture is grounded, not discouraged.",
    },
    {
        'key': 'goal_military_why', 'section': 'goals_future',
        'text': "What draws you to the military, and what do you want to walk out with - a trade, money for school, something else?",
        'framework': ['SFBT:goal'], 'asca': ['B-LS 9', 'M 6'], 'domain': 'career',
        'answer_type': 'text', 'when': 'any', 'pathways': ['military'],
        'coach': "Their answer should shape the recruiter meeting: which job, which benefits, all in writing.",
    },

    # --- barriers_coping --------------------------------------------------
    {
        'key': 'bar_whats_in_the_way', 'section': 'barriers_coping',
        'text': "What's getting in the way right now - time, money, paperwork, family stuff, or not knowing where to start?",
        'framework': ['ASCA'], 'asca': ['B-SMS 6'], 'domain': 'career',
        'answer_type': 'text', 'when': 'any', 'pathways': ['all'],
        'coach': "List them without solving yet; 'not knowing where to start' is the most common and the easiest to fix.",
    },
    {
        'key': 'bar_most_doable', 'section': 'barriers_coping',
        'text': "Of all that, which piece feels the most doable to chip away at first?",
        'framework': ['SFBT:next_step'], 'asca': ['B-SMS 6', 'B-LS 1'], 'domain': 'career',
        'answer_type': 'text', 'when': 'any', 'pathways': ['all'],
        'coach': "Let them choose, even if you'd pick a different one - ownership matters more than order.",
    },
    {
        'key': 'cope_kept_going', 'section': 'barriers_coping',
        'text': "How have you kept going with all of this on your plate?",
        'framework': ['SFBT:coping'], 'asca': ['B-SMS 7', 'B-SMS 5'], 'domain': 'social_emotional',
        'answer_type': 'text', 'when': 'any', 'pathways': ['all'],
        'coach': "Treat every answer as a skill - 'you kept showing up' is a coping strategy worth naming.",
    },
    {
        'key': 'cope_what_helps', 'section': 'barriers_coping',
        'text': "When things get heavy, what actually helps you - even a little? And on the hardest days, what stops it from being worse?",
        'framework': ['SFBT:coping'], 'asca': ['B-SMS 7', 'M 1'], 'domain': 'social_emotional',
        'answer_type': 'text', 'when': 'any', 'pathways': ['all'],
        'coach': "Write these into the stress-plan checklist item; if nothing helps or they mention hurting themselves, follow your safety protocol now.",
    },
    {
        'key': 'bar_family', 'section': 'barriers_coping',
        'text': "Is there anything your family expects, needs or worries about that we should plan around?",
        'framework': ['ASCA'], 'asca': ['B-SS 3', 'B-SMS 6'], 'domain': 'social_emotional',
        'answer_type': 'text', 'when': 'first', 'pathways': ['all'],
        'coach': "For mixed-status or undocumented families, say plainly that the Dream Act application is confidential and not shared with immigration, and that you'll keep their information private.",
    },
    {
        'key': 'bar_money', 'section': 'barriers_coping',
        'text': "If money is part of the worry, what have you heard about how paying for this works? Let's check what's true.",
        'framework': ['ASCA'], 'asca': ['M 6', 'B-LS 9'], 'domain': 'career',
        'answer_type': 'text', 'when': 'any', 'pathways': ['all'],
        'coach': "Many first-gen students believe sticker price is the real price; walk through net cost, Promise, Cal Grant and the Middle Class Scholarship, or paid apprenticeships for workforce students.",
    },
    {
        'key': 'bar_deadline_weeks', 'section': 'barriers_coping',
        'text': "What's your plan for the weeks when deadlines pile up - what will you do, and who will you tell?",
        'framework': ['SFBT:coping', 'SFBT:goal'], 'asca': ['B-SMS 7', 'B-LS 3'], 'domain': 'social_emotional',
        'answer_type': 'text', 'when': 'any', 'pathways': ['all'],
        'coach': "Point at the deadline list and pick the heaviest two weeks together; a plan made now is easier than one made in November.",
    },

    # --- support_relationships --------------------------------------------
    {
        'key': 'sup_who_notices_first', 'section': 'support_relationships',
        'text': "Who would notice first when things are going better for you? What would they notice?",
        'framework': ['SFBT:relationship'], 'asca': ['B-SS 3', 'B-SS 2'], 'domain': 'social_emotional',
        'answer_type': 'text', 'when': 'any', 'pathways': ['all'],
        'coach': "The person they name is a candidate for the support-person checklist item.",
    },
    {
        'key': 'sup_go_to_adult', 'section': 'support_relationships',
        'text': "Who's one adult - here at school or at home - you can go to when you're stuck on this?",
        'framework': ['SFBT:relationship'], 'asca': ['B-SS 3'], 'domain': 'social_emotional',
        'answer_type': 'text', 'when': 'first', 'pathways': ['all'],
        'coach': "If no one comes to mind, offer yourself and one other adult on campus by name and room number.",
    },
    {
        'key': 'sup_forms_helper', 'section': 'support_relationships',
        'text': "Who can sit with you when you do the FAFSA or Dream Act application? Who in your family has the tax or income information?",
        'framework': ['SFBT:relationship'], 'asca': ['B-SS 3', 'B-SS 8'], 'domain': 'career',
        'answer_type': 'text', 'when': 'any', 'pathways': COLLEGE_BOUND,
        'coach': "If the answer is 'nobody', book them into a Cash for College or school aid workshop before they leave the room.",
    },
    {
        'key': 'sup_peer_checkin', 'section': 'support_relationships',
        'text': "Who's a friend going through the same thing you could check in with each week?",
        'framework': ['SFBT:relationship'], 'asca': ['B-SS 2', 'B-SS 6'], 'domain': 'social_emotional',
        'answer_type': 'text', 'when': 'any', 'pathways': ['all'],
        'coach': "Suggest a standing time - 'Sunday night, five minutes, what's due this week' - and let them set it.",
    },
    {
        'key': 'sup_advocate_practice', 'section': 'support_relationships',
        'text': "If a college, program or employer isn't getting back to you, what would you say when you call or email? Let's practice it once.",
        'framework': ['ASCA'], 'asca': ['B-SS 8', 'B-SS 1'], 'domain': 'career',
        'answer_type': 'text', 'when': 'any', 'pathways': ['all'],
        'coach': "Draft the two-sentence email together and have them send it from the room if one is actually pending.",
    },

    # --- next_step --------------------------------------------------------
    {
        'key': 'next_one_small_step', 'section': 'next_step',
        'text': "What's one small thing you'll do before we meet again - something you could finish in under an hour?",
        'framework': ['SFBT:next_step'], 'asca': ['B-SMS 1', 'B-LS 7'], 'domain': 'career',
        'answer_type': 'text', 'when': 'any', 'pathways': ['all'],
        'coach': "Keep it theirs and keep it small; if they pick something big, ask what the first hour of it would be.",
    },
    {
        'key': 'next_when_exactly', 'section': 'next_step',
        'text': "When exactly will you do it - what day, what time, where will you be? And what's the very first move: opening the website, texting your mom, asking a teacher?",
        'framework': ['SFBT:next_step'], 'asca': ['B-LS 3', 'B-SMS 1'], 'domain': 'academic',
        'answer_type': 'text', 'when': 'any', 'pathways': ['all'],
        'coach': "Put the date in the plan before they leave; a step without a date is a wish - and if the first move takes two minutes, do it now.",
    },
    {
        'key': 'next_how_know_done', 'section': 'next_step',
        'text': "How will you know it's done? What will you be able to show me?",
        'framework': ['SFBT:goal'], 'asca': ['B-LS 6', 'B-SMS 3'], 'domain': 'academic',
        'answer_type': 'text', 'when': 'any', 'pathways': ['all'],
        'coach': "A screenshot, a confirmation email, a name - make the finish line concrete.",
    },
    {
        'key': 'next_what_might_stop', 'section': 'next_step',
        'text': "What might get in the way, and what will you do if it does?",
        'framework': ['SFBT:next_step'], 'asca': ['B-SMS 6', 'B-SMS 2'], 'domain': 'social_emotional',
        'answer_type': 'text', 'when': 'any', 'pathways': ['all'],
        'coach': "An 'if-then' plan ('if the site is down, I'll try Thursday at lunch in the library') doubles follow-through.",
    },
    {
        'key': 'next_confidence', 'section': 'next_step',
        'text': "0 to 10, how sure are you that you'll get it done by then? What would make it a 9?",
        'framework': ['SFBT:scaling', 'SFBT:next_step'], 'asca': ['M 4', 'B-SMS 5'], 'domain': 'career',
        'answer_type': 'scale', 'when': 'any', 'pathways': ['all'],
        'coach': "Under 7, shrink the step or move the date until they're at 8 or above - don't send them out with a step they don't believe in.",
    },

    # --- closing ----------------------------------------------------------
    {
        'key': 'close_compliment', 'section': 'closing',
        'text': "Here's what I noticed today: [one specific thing they did or said]. That's going to serve you well after June.",
        'framework': ['SFBT:compliment'], 'asca': ['M 4', 'M 5'], 'domain': 'social_emotional',
        'answer_type': 'none', 'when': 'any', 'pathways': ['all'],
        'coach': "Name an action from this meeting, not a trait - 'you already made your FSA ID' beats 'you're responsible'.",
    },
    {
        'key': 'close_takeaway', 'section': 'closing',
        'text': "What's the one thing you're taking with you from today?",
        'framework': ['SFBT:goal'], 'asca': ['B-LS 1', 'M 4'], 'domain': 'academic',
        'answer_type': 'text', 'when': 'any', 'pathways': ['all'],
        'coach': "If it isn't the next step, gently restate the step and the date so both are in their head.",
    },
    {
        'key': 'close_anything_else', 'section': 'closing',
        'text': "Is there anything we didn't get to that you wanted to talk about?",
        'framework': ['ASCA'], 'asca': ['M 2', 'B-SS 1'], 'domain': 'social_emotional',
        'answer_type': 'text', 'when': 'any', 'pathways': ['all'],
        'coach': "The real reason for the visit sometimes shows up here; if it's big, book a separate time rather than rushing it.",
    },
    {
        'key': 'close_next_meeting', 'section': 'closing',
        'text': "When should we meet again? Let's put it on the calendar right now.",
        'framework': ['SFBT:next_step'], 'asca': ['B-SS 3', 'B-SMS 10'], 'domain': 'career',
        'answer_type': 'text', 'when': 'any', 'pathways': ['all'],
        'coach': "Schedule it before they stand up, ideally within two to four weeks of the step's date.",
    },
]

QUESTION_KEYS = [q['key'] for q in QUESTIONS]

# ---------------------------------------------------------------------------
# 6. Helpers (pure)
# ---------------------------------------------------------------------------


def items_for_pathway(pathway):
    """Checklist items that apply to ``pathway`` (or to everyone)."""
    return [i for i in CHECKLIST if 'all' in i['pathways'] or pathway in i['pathways']]


def questions_for(section, when='any'):
    """Questions in ``section`` for a ``when`` of 'first', 'followup' or 'any'.

    A question whose ``when`` is 'any' matches both meeting types, and asking
    for ``when='any'`` returns every question in the section.
    """
    return [
        q for q in QUESTIONS
        if q['section'] == section and (when == 'any' or q['when'] == 'any' or q['when'] == when)
    ]


def deadlines_for_pathway(pathway):
    """Deadline defaults that apply to ``pathway`` (or to everyone), in date order."""
    return [d for d in DEADLINE_DEFAULTS if 'all' in d['pathways'] or pathway in d['pathways']]


# ---------------------------------------------------------------------------
# Self-check (pure; returns a list of problems, empty when clean)
# ---------------------------------------------------------------------------


def validate():
    problems = []

    def _dup(name, keys):
        seen = set()
        for k in keys:
            if k in seen:
                problems.append('%s: duplicate key %r' % (name, k))
            seen.add(k)

    _dup('CHECKLIST', CHECKLIST_KEYS)
    _dup('QUESTIONS', QUESTION_KEYS)
    _dup('DEADLINE_DEFAULTS', DEADLINE_KEYS)

    for c in CHECKLIST:
        k = c['key']
        if c['group'] not in CHECKLIST_GROUP_KEYS:
            problems.append('CHECKLIST %s: bad group %r' % (k, c['group']))
        if c['maps_to'] is not None and c['maps_to'] not in PLAN_FIELD_TARGETS:
            problems.append('CHECKLIST %s: maps_to %r not an allowed plan field' % (k, c['maps_to']))
        if c['deadline_key'] is not None and c['deadline_key'] not in DEADLINE_KEYS:
            problems.append('CHECKLIST %s: unknown deadline_key %r' % (k, c['deadline_key']))
        if c['season'] not in SEASONS:
            problems.append('CHECKLIST %s: bad season %r' % (k, c['season']))
        for p in c['pathways']:
            if p not in PATHWAY_KEYS:
                problems.append('CHECKLIST %s: bad pathway %r' % (k, p))
        if not c['help'] or not c['label']:
            problems.append('CHECKLIST %s: missing label or help' % k)

    for q in QUESTIONS:
        k = q['key']
        if q['section'] not in SECTION_KEYS:
            problems.append('QUESTIONS %s: bad section %r' % (k, q['section']))
        if not 1 <= len(q['asca']) <= 3:
            problems.append('QUESTIONS %s: needs 1-3 ASCA codes' % k)
        for code in q['asca']:
            if code not in ASCA_STANDARDS:
                problems.append('QUESTIONS %s: unknown ASCA code %r' % (k, code))
        for tag in q['framework']:
            if tag not in FRAMEWORK_TAGS:
                problems.append('QUESTIONS %s: unknown framework tag %r' % (k, tag))
        if q['domain'] not in ASCA_DOMAIN_KEYS:
            problems.append('QUESTIONS %s: bad domain %r' % (k, q['domain']))
        if q['answer_type'] not in ('text', 'scale', 'none'):
            problems.append('QUESTIONS %s: bad answer_type %r' % (k, q['answer_type']))
        if q['when'] not in ('first', 'followup', 'any'):
            problems.append('QUESTIONS %s: bad when %r' % (k, q['when']))
        for p in q['pathways']:
            if p not in PATHWAY_KEYS:
                problems.append('QUESTIONS %s: bad pathway %r' % (k, p))
        if not q['text'] or not q['coach']:
            problems.append('QUESTIONS %s: missing text or coach' % k)

    import re as _re
    for q in QUESTIONS:
        if _re.search(r'\b20\d\d\b', q['text']):
            problems.append('QUESTIONS %s: text embeds a calendar year' % q['key'])
    for c in CHECKLIST:
        if _re.search(r'\b20\d\d\b', c['help']):
            problems.append('CHECKLIST %s: help embeds a calendar year' % c['key'])

    prev = ''
    for d in DEADLINE_DEFAULTS:
        k = d['key']
        if len(d['date']) != 10 or d['date'][4] != '-' or d['date'][7] != '-':
            problems.append('DEADLINE %s: bad date %r' % (k, d['date']))
        if d['date'] < prev:
            problems.append('DEADLINE %s: out of date order' % k)
        prev = d['date']
        if d['category'] not in ('application', 'financial_aid', 'testing', 'decision', 'records', 'other'):
            problems.append('DEADLINE %s: bad category %r' % (k, d['category']))
        if not isinstance(d['verify'], bool):
            problems.append('DEADLINE %s: verify must be bool' % k)
        for p in d['pathways']:
            if p not in PATHWAY_KEYS:
                problems.append('DEADLINE %s: bad pathway %r' % (k, p))

    # Every SFBT element the feature promises is present at least once.
    required_tags = set(FRAMEWORK_TAGS)
    used_tags = {t for q in QUESTIONS for t in q['framework']}
    for t in sorted(required_tags - used_tags):
        problems.append('QUESTIONS: framework tag %r never used' % t)
    if not any(q['when'] == 'followup' and 'SFBT:whats_better' in q['framework'] for q in QUESTIONS):
        problems.append("QUESTIONS: no 'what's better' question for follow-up visits")
    if not questions_for('next_step', 'first') or not questions_for('next_step', 'followup'):
        problems.append('QUESTIONS: next_step section must apply to both meeting types')

    return problems
