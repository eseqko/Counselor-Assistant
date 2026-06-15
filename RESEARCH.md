# Vital Data for School Counselor Success

A research-informed reference for what a successful K-12 school counselor should be capturing, watching, and acting on — synthesized from ASCA standards, California Education Code, peer-reviewed dropout-prediction research, and established practitioner frameworks (Attendance Works, Mapp/Hatching Results/Education Trust, NCII/PBIS, NTAC/NASP).

The goal of this document is twofold:

1. **For the counselor** — a concise, cited list of what the literature says are the highest-leverage data points to track, with thresholds and benchmarks.
2. **For the app** — the research that justifies what's currently built and surfaces what's worth building next. Each section closes with a *"App coverage"* note marking what's already implemented vs. what's a gap.

The app is California-focused (a-g, ELPAC, AB graduation exemptions, state-minimum diploma, EC 48985 translation thresholds), so CA/CDE context is weighted, with ASCA standards as the national backbone.

---

## If you track only 10 things, track these

For a counselor with no time and no tools, this is the highest-leverage set:

| # | Indicator | Threshold | Why |
|---|---|---|---|
| 1 | **Chronic absenteeism** (≥10% days absent YTD) | Tier 2 at 5–9.9%, Tier 3 at ≥20% | Strongest single dropout predictor across all grades ([Attendance Works](https://www.attendanceworks.org/chronic-absence/addressing-chronic-absence/3-tiers-of-intervention/); [Balfanz & Byrnes, 2012](https://new.every1graduates.org/wp-content/uploads/2012/05/FINALChronicAbsenteeismReport_May16.pdf)) |
| 2 | **9th-grade On-Track** | ≥5 full-year credits AND ≤1 semester F in a core course | On-track 9th graders graduate at 81% vs. 22% off-track ([Allensworth & Easton, 2007, UChicago](https://consortium.uchicago.edu/sites/default/files/2018-10/07%20What%20Matters%20Final.pdf)) |
| 3 | **6th-grade ABCs** | Any one of: failing English or math, attendance <80%, unsatisfactory behavior | ~75% dropout rate when triggered ([Balfanz, Herzog & Mac Iver, 2007](https://new.every1graduates.org/tools-and-models/early-warning-and-response-systems/)) |
| 4 | **Office Discipline Referrals (ODRs)** | 0–1 Tier 1; 2–5 Tier 2; ≥6 Tier 3 | 79% of end-of-year 6+ ODR students hit 2 by December — screen early ([PBIS ODR Brief, McIntosh et al.](https://assets-global.website-files.com/5d3725188825e071f1670246/5d7979befedbb681be830b04_final-odr-brief.pdf)) |
| 5 | **a-g progress** (CA) | 15 yearlong courses, C or better, 11 before senior year | UC/CSU gatekeeper; predicts college-going ([UC Admissions](https://admission.universityofcalifornia.edu/admission-requirements/first-year-requirements/subject-requirement-a-g.html)) |
| 6 | **Credit pace** | District 220-credit plan ≈ 55/year; state minimum 130 (EC §51225.3) | Quarter-aware projections beat end-of-year-only checks ([CDE](https://www.cde.ca.gov/ci/gs/hs/hsgrmin.asp)) |
| 7 | **PHQ-A score** | ≥10 = moderate, clinical follow-up; item 9 endorsement triggers C-SSRS | Standard adolescent depression screen ([AAP-aligned](https://hiboop.com/assessments/phq-a/)) |
| 8 | **C-SSRS triage** | Q3–5 = moderate/high; Q6 = imminent | The validated frame for suicide risk in schools ([Columbia Lighthouse](https://cssrs.columbia.edu/the-columbia-scale-c-ssrs/about-the-scale/)) |
| 9 | **FAFSA/CADAA status** | AB 469 requires all 12th graders complete or sign opt-out | CA completion fell to <50% in 2024, rebounding to ~55.8% by July 2025 ([NCAN, 2025](https://www.ncan.org/news/705304/FAFSA-Completions-Bounce-Back-with-Class-of-2025-Return-to-Pre-Pandemic-Rates.htm)) |
| 10 | **Subgroup disparity ratio** | Subgroup % of (suspensions, AP enrollment, FAFSA) ÷ subgroup % of enrollment; flag if discipline ratio >1.5 or AP ratio <0.8 | Black students were 18% of K-12 suspensions vs. 8% of enrollment in 2020–21 ([OCR CRDC](https://www.ed.gov/sites/ed/files/about/offices/list/ocr/docs/crdc-discipline-school-climate-report.pdf)) |

---

## Domain 1 — ASCA National Model alignment

**Capture for each ASCA component:**

- **Define:** alignment to ASCA Student Standards (Mindsets & Behaviors), Professional Standards, Ethical Standards.
- **Manage:** annual calendar, advisory council, Use-of-Time assessment, Annual Student Outcome Goal plan, Closing-the-Gap Action Plan ([ASCA Templates](https://www.schoolcounselor.org/About-School-Counseling/ASCA-National-Model-for-School-Counseling-Programs/Templates-Resources)).
- **Deliver:** direct services (instruction, appraisal/advisement, counseling) + indirect (consultation, collaboration, referrals) per student or group.
- **Assess:** *process* data (who/what/how many), *perception* data (knowledge/attitude/skills via "I believe / I know / I can"), *outcome* data (achievement, attendance, discipline) ([ASCA, 2018](https://www.schoolcounselor.org/newsletters/october-2018/types-of-data-to-measure-school-counseling-program)).

**Benchmarks:**

- Use-of-Time: **≥80% direct + indirect services**, ≤20% planning/school support, measured across ≥10 sample days/year ([Hatching Results, 2023](https://www.hatchingresults.com/blog/2023/5/use-of-time-assessment-a-driver-for-change)).
- Student-counselor ratio: **250:1** ([ASCA](https://www.schoolcounselor.org/about-school-counseling/school-counselor-roles-ratios)).
- Annual outcome goals must be SMART with numeric baseline AND target on achievement, attendance, OR discipline (e.g., "reduce chronic absence from 48.6% to 40%").

**App coverage:** ✅ Activity Log captures the 4 ASCA service types and 250+ categories; ✅ Use-of-Time Report computes the 80/20 split; ✅ Reports/ASCA Results and Closing-the-Gap pages exist; ⚠️ Outcome-goal SMART tracking is supported through individual goals but no annual program-level outcome-goal dashboard yet.

---

## Domain 2 — Early Warning System (the ABCs)

**Attendance, Behavior, Course performance — the dropout-predictor triad.**

- **Chronic absenteeism:** missing ≥10% of enrolled days, any reason ([Balfanz & Byrnes, 2012](https://new.every1graduates.org/wp-content/uploads/2012/05/FINALChronicAbsenteeismReport_May16.pdf)). A district can hit 90% ADA while up to 40% of students are chronically absent.
- **9th-grade On-Track:** ≥5 full-year credits + ≤1 semester F in a core course ([UChicago CCSR, 2007](https://consortium.uchicago.edu/sites/default/files/2018-10/07%20What%20Matters%20Final.pdf)).
- **6th-grade ABCs:** any one of failing English or math, attendance <80%, unsatisfactory behavior in a core course → 10–20% on-time graduation odds ([Balfanz, Herzog & Mac Iver, 2007](https://new.every1graduates.org/tools-and-models/early-warning-and-response-systems/)).
- **Behavior tier (PBIS norms):** 0–1 ODR Tier 1 (~80% of students), 2–5 ODR Tier 2 (~15%), ≥6 ODR Tier 3 (~5%) ([PBIS ODR Brief](https://assets-global.website-files.com/5d3725188825e071f1670246/5d7979befedbb681be830b04_final-odr-brief.pdf)).
- **Course flags:** GPA <2.0, any F in core math/ELA, D/F rate ≥20% ([US Dept of Ed EWS Brief](https://www.ed.gov/sites/ed/files/rschstat/eval/high-school/early-warning-systems-brief.pdf)).
- **What Works Clearinghouse Practice Guide** *Preventing Dropout in Secondary Schools* (NCEE 2017-4028): monitor the ABCs longitudinally + provide targeted intensive support ([IES/WWC](https://ies.ed.gov/ncee/wwc/PracticeGuide/24)).

**App coverage:** ✅ Early Warning Report flags students by attendance/grades/referrals; ✅ Insights 360 surfaces D/F by class/period/teacher and compounding-risk overlap; ✅ Smart Alerts engine; ⚠️ Behavior/ODR ingestion (suspension data, discipline incidents) is not modeled — currently only via referrals.

---

## Domain 3 — MTSS / RTI data

**Tier 2 design:** small groups 3–7 students, 20–30 min, 3–5×/week, 8–20 week cycles, **progress monitor at least bi-weekly** ([Center on MTSS](https://mtss4success.org/)).

**Tier 3 design:** individual / 1–3 student groups, 30+ min, daily, **weekly progress monitoring** ([NCII DBI](https://intensiveintervention.org/data-based-individualization)).

**Decision rules:**

- Collect **6–9 data points** before applying a rule.
- **Four-point rule:** 4 consecutive points below the goal line = non-responder; intensify or change. 4 above = raise the goal ([NCII DBI Framework](https://intensiveintervention.org/sites/default/files/DBI_Framework.pdf)).
- **Fidelity of implementation:** structured observation tools ≥3×/cycle; "adequate fidelity" cut typically ≥80% of intervention steps as designed.

**App coverage:** ✅ MTSS/RTI module exists with intervention plans, tiers, progress notes, review-date reminders; ⚠️ Decision rules (4-point, goal-line slope, DBI Step 3 prompt) aren't auto-applied — currently counselor-judgment; ⚠️ Fidelity-of-implementation scoring isn't a field on the intervention model.

---

## Domain 4 — Academic & graduation tracking (CA)

- **CA state minimum diploma: 130 credits** (EC §51225.3) — 3 yr English, 2 yr math (incl. Algebra I), 2 yr science, 3 yr social studies, 1 yr VAPA/LOTE/CTE, 2 yr PE ([CDE](https://www.cde.ca.gov/ci/gs/hs/hsgrmin.asp)).
- **District typical: 220 credits / 55 per year.**
- **a-g UC/CSU minimum:** 15 yearlong courses, C or better, 11 completed before senior year ([UC Admissions](https://admission.universityofcalifornia.edu/admission-requirements/first-year-requirements/subject-requirement-a-g.html)).
- **AB 167/216 (foster), AB 1806 (homeless), AB 2121 (newcomer/migrant), AB 365 (military):** transfers after 2nd year of HS who can't reasonably complete district requirements in 4 years are entitled to graduate under the **130-credit state minimum** ([CDE Foster Youth Rights](https://www.cde.ca.gov/ls/pf/fy/fyedrights.asp)).
- **ELPAC RFEP criteria** (4 per Ed Code §313(f)): Summative ELPAC Overall PL 4 + teacher evaluation + parent consultation + basic-skills comparison ([CDE Reclassification](https://www.cde.ca.gov/sp/ml/reclassification.asp)).
- **2024–25 statewide 4-yr cohort graduation rate: 87.5%** ([CDE, 2025](https://www.cde.ca.gov/nr/ne/yr25/yr25rel49.asp)).

**App coverage:** ✅ Graduation Tracker with credit pace + a-g + CTE pathway; ✅ State-minimum risk surfaced alongside district risk; ✅ AB exemption tracking on each student profile; ✅ AI insights frame credits/a-g against grade × quarter and project WIP credits; ✅ End-of-year rollover honors all five AB-population skip defaults. **Fully covered.**

---

## Domain 5 — College & Career Readiness

- **AB 469 (2021):** every LEA must ensure 12th graders complete **FAFSA, CADAA, or signed opt-out**, beginning class of 2023 ([CSAC](https://www.csac.ca.gov/post/ab-469-fafsacadaa-completion-requirement-and-opt-out-form)).
- **CA FAFSA/CADAA completion:** 74% in 2023; <50% in 2024 post-redesign; rebounded to ~55.8% by July 2025 ([NCAN, 2025](https://www.ncan.org/news/705304/FAFSA-Completions-Bounce-Back-with-Class-of-2025-Return-to-Pre-Pandemic-Rates.htm)).
- **CA CCI "Prepared" pathways:** a-g + SBAC Standard Met; OR CTE completer + a-g/Nearly Met; OR 2 AP/IB at 3+/4+; OR SBAC-aligned SAT/ACT; OR state seal (biliteracy/CTE); OR 9+ semester dual-enrollment units ([CDE CCI Toolkit 2025](https://www.cde.ca.gov/ta/ac/cm/documents/collegecareer25.pdf)).
- **CTE pathway:** participant → concentrator (≥2 courses in a single Perkins V pathway) → completer (capstone, C- or better) ([CALPADS](https://documentation.calpads.org/Glossary/EndofYearData/CareerTechnicalEducation(CTE)Participant/)).
- **Summer melt:** 10–20% of college-intending seniors don't enroll; up to 40% for low-income/CC-bound; **2–3 hours of targeted counselor outreach lifts enrollment 3–4 pp overall, 8 pp for low-income** ([Castleman & Page, 2014](https://eric.ed.gov/?id=ED568799); [SDP Summer Melt Tools](https://sdp.cepr.harvard.edu/summer-melt-tools)).
- **Undermatch:** majority of high-achieving low-income students never apply to a single selective college that would cost them less than where they enroll ([Hoxby & Avery, NBER w18586](https://www.nber.org/papers/w18586)).

**App coverage:** ✅ College & Career module tracks pathway, GPA, test scores, applications, FAFSA status; ⚠️ AB 469 status as a discrete field (submitted / opted-out / pending) isn't enforced separately; ⚠️ Summer-melt outreach workflow (July–August reminder cadence) is a gap; ⚠️ Match/fit flagging on a student's college list isn't computed.

---

## Domain 6 — Equity & access

**Required disaggregation:** race/ethnicity (per CA Dashboard), EL status + RFEP, SED/FRPL, foster/homeless/migrant, IEP/504, gender, optionally LGBTQ+ self-ID ([CDE DataQuest](https://www.cde.ca.gov/ds/cm/dqhighlights.asp)).

**Benchmarks:**

- ASCA ratio: **250:1**. US average 2024–25: **372:1**; CA average: **~432:1** (elementary 737:1, HS 232:1) ([ASCA Ratios](https://www.schoolcounselor.org/getmedia/f2a319d5-db73-4ca1-a515-2ad2c73ec746/Ratios-2023-24-Alpha.pdf); [EdSource, 2026](https://edsource.org/updates/student-to-counselor-ratio-improves-nationwide-analysis-finds)).
- **ASCA Ethical Standard A.10 "Marginalized Populations" (2022):** counselors actively dismantle systemic barriers and examine implicit bias ([ASCA Ethical Standards 2022](https://www.schoolcounselor.org/getmedia/44f30280-ffe8-4b41-9ad8-f15909c3d164/EthicalStandards.pdf)).
- **OCR CRDC disparity flags:** Black boys = 8% K-12 enrollment but **18% in-school + 22% out-of-school suspensions**. Flag any subgroup whose discipline rate exceeds **enrollment share × 1.5** ([OCR CRDC 2020–21](https://www.ed.gov/sites/ed/files/about/offices/list/ocr/docs/crdc-discipline-school-climate-report.pdf)).
- **AP access gap:** flag subgroup AP enrollment share < (subgroup enrollment × 0.8); AP pass-rate gap >10 pp from school average.

**App coverage:** ✅ Equity Report exists; ✅ Closing the Gap; ✅ Caseload Equity (admin); ⚠️ Auto-computed disparity ratios with threshold flags (the 1.5× and 0.8× rules) aren't surfaced as a single "equity lens" toggle on every roster yet.

---

## Domain 7 — Social-emotional / mental health

**Validated screeners + cutoffs:**

- **PHQ-A** (adolescent PHQ-9, ages 11–17): 0–4 minimal, 5–9 mild, **10–14 moderate**, **15–19 moderately severe**, 20–27 severe. **Item 9 endorsement triggers immediate C-SSRS** ([AAP PHQ-A](https://hiboop.com/assessments/phq-a/)).
- **GAD-7:** 0–4 minimal, 5–9 mild, **10–14 moderate**, 15–21 severe; ≥10 warrants further evaluation ([Dartmouth-Hitchcock](https://www.dartmouth-hitchcock.org/sites/default/files/2021-02/gad-7-anxiety-scale.pdf)).
- **SAEBRS / mySAEBRS:** total ≤36 = at risk (Social ≤12, Academic ≤9, Emotional ≤17) ([Kilgus et al., 2018](https://pubmed.ncbi.nlm.nih.gov/29629792/); [Renaissance SAEBRS](https://www.renaissance.com/products/assessment/saebrs/)).
- **BIMAS-2:** multi-informant T-scores on Conduct, Negative Affect, Cognitive/Attention, Social, Academic Functioning ([WPS BIMAS-2](https://www.wpspublish.com/bimas-2-the-behavior-intervention-monitoring-assessment-system-2.html)).
- **C-SSRS Screener:** Q1–2 = low; **Q3–5 = moderate/high → mental health referral**; **Q6 = imminent risk → emergency services** ([Columbia](https://cssrs.columbia.edu/the-columbia-scale-c-ssrs/about-the-scale/); [SAMHSA](https://www.samhsa.gov/resource/dbhis/columbia-suicide-severity-rating-scale-c-ssrs)).
- **SAFE-T 5 steps:** risk factors → protective factors → suicide inquiry → risk level + intervention → documented plan ([SAMHSA SAFE-T](https://library.samhsa.gov/product/safe-t-suicide-assessment-five-step-evaluation-and-triage/pep24-01-036)).

**CA legal:**

- **AB 2246 (EC §215)** — LEAs serving grades 7–12 must adopt suicide prevention/intervention/postvention policy; address high-risk groups (LGBTQ, bereaved, prior attempts, foster) ([AB 2246](https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=201520160AB2246)).
- **AB 1767 (2019)** — extends EC §215 to grades K–6 ([AB 1767](https://leginfo.legislature.ca.gov/faces/billTextClient.xhtml?bill_id=201920200AB1767)).

**App coverage:** ✅ Screeners module exists (ACEs, RIASEC, etc.); ⚠️ Validated mental-health screeners (PHQ-A, GAD-7, SAEBRS, C-SSRS) with band-colored cutoffs aren't built in; ⚠️ AB 2246 postvention/re-entry workflow + SAFE-T documentation form would be valuable additions. **This is the largest current gap.**

---

## Domain 8 — Attendance specifics (CA)

**Attendance Works tiers:**

- Satisfactory: **0–4.9%** absent
- At-Risk: **5–9.9%**
- Moderate Chronic: **10–19.9%** (~18–35 days/yr)
- Severe Chronic: **≥20%** ([Attendance Works tier guide](https://www.attendanceworks.org/chronic-absence/addressing-chronic-absence/3-tiers-of-intervention/))
- **Early-warning trigger: 2+ absences in any month** ([Early Education Toolkit](https://www.attendanceworks.org/resources/toolkits/early-education-toolkit/chronic-absence/)).

**CA truancy (Ed Code):**

- **EC 48260** — **truant** after 3 unexcused absences or tardies >30 min in one school year.
- **EC 48262** — **habitual truant** after a 3rd truancy report + at least one parent conference attempt.
- **EC 48263** — **SARB referral** (or DA mediation).
- **EC 48263.6** — **chronic truant**: ≥10% of school days without valid excuse + parental conscientious efforts exhausted ([CDE Truancy](https://www.cde.ca.gov/ls/ai/tr/); [CDE Terminology](https://www.cde.ca.gov/ls/ai/ag/ag-terminology-laws.asp)).

**App coverage:** ✅ Attendance import + Early Warning + Insights 360 absences-by-period/weekday + chronic-absenteeism flag in analytics. ⚠️ Stepped truancy workflow (EC 48260 letter → EC 48262 conference → EC 48263 SARB packet) with auto-generated dated notices isn't built.

---

## Domain 9 — Family / guardian communication

- **CA EC §48985** — when ≥15% of a school's pupils speak a single primary language other than English, all notices/reports/records to parents **must be translated** into that language ([Cal Ed Code 48985](https://codes.findlaw.com/ca/education-code/edc-sect-48985/); [CDE Clearinghouse FAQ](https://www.cde.ca.gov/ls/pf/cm/cmdfaq.asp)).
- **Mapp Dual-Capacity Framework v2 (2019)** — effective family engagement is process-oriented (relational, linked-to-learning, developmental, collaborative, **interactive**) and organizational (systemic, integrated, sustained). Log whether each contact is **two-way (dialogue)** vs **one-way (notification)** because two-way is the evidence-based driver ([Mapp & Bergman, 2019, USED](https://www.ed.gov/media/document/41-dual-capacity-building-framework-family-school-partnerships-109231.pdf)).
- **Operational cadence many CA LEAs use:** ≥1 positive two-way contact within first 30 days, quarterly after that; **EL families: contact attempted in home language each cycle**.

**App coverage:** ✅ Communication Log captures mode/direction/subject/follow-up; ✅ Drafts/Mail Merge can produce bulk personalized letters; ⚠️ Auto-translation when the school crosses the EC 48985 15% threshold isn't enforced; ⚠️ "Days-since-last-meaningful-two-way-contact" per student against a Mapp cadence target would be a strong addition.

---

## Domain 10 — Counselor workload / sustainability

- **ASCA recommended ratio: 250:1** (unchanged since 1965).
- **National 2024–25 ratio: 372:1** ([ASCA Ratios](https://www.schoolcounselor.org/About-School-Counseling/School-Counselor-Roles-Ratios)).
- **California 2024–25: ~432:1** — elementary 737:1, HS 232:1 ([EdSource, 2026](https://edsource.org/updates/student-to-counselor-ratio-improves-nationwide-analysis-finds)).
- **Use-of-time benchmark: ≥80% direct + indirect services.**
- **Burnout predictors:** high caseload + role ambiguity is the dominant predictor of personal-accomplishment loss ([Niles et al., 2024, *J. Counseling & Dev.*](https://onlinelibrary.wiley.com/doi/full/10.1002/jcad.12530)). "Advocacy burnout" is an emerging construct ([Turner et al., 2025, *Prof. School Counseling*](https://journals.sagepub.com/doi/10.1177/2156759X251403475)).

**App coverage:** ✅ Use-of-Time Report computes the 80/20 split; ✅ Caseload Equity (admin) compares team distribution; ⚠️ Live ratio vs. ASCA 250:1 / CA 432:1 baseline on every counselor's dashboard isn't surfaced; ⚠️ Fair-share / non-counseling duty tracking is implicit, not first-class.

---

## Domain 11 — Crisis & safety

**Threat assessment (NTAC / NASP):**

- **NTAC 8-step framework:** (1) multidisciplinary team; (2) define prohibited & concerning behaviors; (3) central reporting mechanism; (4) law-enforcement threshold; (5) assessment procedure; (6) risk-management options; (7) connected climate; (8) training ([NTAC Operational Guide, 2018](https://www.secretservice.gov/protection/ntac)).
- **BTAM levels:** low / moderate / high / imminent ([NASP BTAM Best Practice](https://www.nasponline.org/resources-and-publications/resources-and-podcasts/school-safety-and-crisis/systems-level-prevention/threat-assessment-at-school/behavior-threat-assessment-and-management-(btam)-best-practice-considerations-for-k%E2%80%9312-schools)).

**CA mandated reporter (CANRA):**

- Phone report **immediately or as soon as practicably possible** + **written report within 36 hours** (Penal Code §§11164–11174.3; [§11166](https://codes.findlaw.com/ca/penal-code/pen-sect-11166/)).

**Restraint & seclusion (AB 2657 → EC §§49005–49006.4):**

- Last resort; LEAs report annually to CDE within 3 months of school year end, disaggregated by race/gender ([CDE R&S data](https://www.cde.ca.gov/ds/ad/rsdinfo.asp); [AB 2657](https://leginfo.legislature.ca.gov/faces/billTextClient.xhtml?bill_id=201720180AB2657)).

**Involuntary hold (5585/5150):**

- WIC §5585 for minors — up to 72-hour hold; criteria: danger to self / danger to others / gravely disabled ([WIC §5150](https://codes.findlaw.com/ca/welfare-and-institutions-code/wic-sect-5150/)).

**App coverage:** ⚠️ The new counselor system prompt has a hard stop that routes any crisis content back to the counselor's protocol; that's the right floor. **No structured BTAM intake, CANRA timer, or AB 2657 export exists yet** — this is a genuine gap for a school counselor app.

---

## Domain 12 — Emerging trends 2024–2026

- **Chronic absenteeism is the post-pandemic story.** CA 19% in 2024–25 (1.1M students), down from 30% peak but still well above the 12% pre-pandemic baseline; national 23.5% in 2024 ([PACE, 2025](https://edpolicyinca.org/publications/unpacking-californias-chronic-absence-crisis-through-2024-25); [AEI, 2024](https://www.aei.org/research-products/report/lingering-absence-in-public-schools-tracking-post-pandemic-chronic-absenteeism-into-2024/)).
- **Mental-health load:** YRBS 2023 — 40% of HS students report persistent sadness/hopelessness; **20% seriously considered suicide; 9% attempted**; females and LGBTQ+ at sharply higher risk ([CDC YRBS 2023, MMWR Suppl 73(4)](https://www.cdc.gov/mmwr/volumes/73/su/su7304a9.htm)).
- **Universal mental-health screening is spreading:** 30.5% of US K-12 principals report required screening in 2024 (up from 13% in 2016); Illinois was first to mandate grades 3–12 ([EdWeek, 2025](https://www.edweek.org/leadership/a-third-of-public-schools-require-mental-health-screenings-then-what-happens/2025/08)).
- **FAFSA crisis & rebound:** 2024–25 senior completion fell ~11.6% (~300K fewer filers, disproportionately low-income Black/Latino); 2025–26 rebounded to pre-pandemic norms ([NCAN, 2025](https://www.ncan.org/news/705304/FAFSA-Completions-Bounce-Back-with-Class-of-2025-Return-to-Pre-Pandemic-Rates.htm)).
- **Belonging as predictor:** 2024 quasi-experimental US grades 4–5 study (n>8,000) shows the dominant causal direction is **belonging → achievement** (attendance, grades, graduation all follow) ([Frontiers in Psychology, 2024](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2024.1478320/full)).
- **AI in counseling — ASCA's emerging "ASCA-MTSS-AI" framework (2026)** urges human-in-loop, privacy/equity guardrails; flags hallucinations and bias as primary risks ([ASCA, 2026](https://doi.org/10.1177/2156759X261421920)).
- **CA CCI counts middle-grade work-based learning** toward the College/Career Indicator beginning 2025 ([CDE CCI Toolkit 2025](https://www.cde.ca.gov/ta/ac/cm/documents/ccicareer25.pdf)).

---

## Gaps in this app worth considering (prioritized)

In rough order of leverage relative to current coverage:

1. **Validated mental-health screeners with cutoffs.** PHQ-A, GAD-7, SAEBRS, C-SSRS as first-class screener types with band-colored thresholds + auto-routing (item-9 → C-SSRS → SAFE-T). High-leverage given the post-pandemic mental-health load and the spreading universal-screening mandate. (Domain 7.)
2. **Behavior / ODR ingestion.** The "B" of the ABCs is currently the weakest signal in the app — discipline data isn't modeled as such. Adding an ODR table + PBIS-norm tiers would close the early-warning loop. (Domain 2.)
3. **Stepped CA truancy workflow.** EC 48260 → 48262 → 48263 letters + SARB packet generation with EL-language toggle. (Domain 8.)
4. **MTSS decision-rule automation.** Surface the 4-point rule on each intervention progress chart; prompt the DBI Step-3 diagnostic when triggered. Add fidelity-of-implementation scoring. (Domain 3.)
5. **Equity lens toggle.** A one-click subgroup re-render on every roster + auto-computed disparity ratios (1.5× discipline, 0.8× AP). (Domain 6.)
6. **Family communication cadence tracking.** "Days since last two-way contact" per student against a Mapp-aligned target; EL-language flag with EC 48985 auto-enforcement. (Domain 9.)
7. **Live counselor-ratio + use-of-time widget.** Each counselor's current ratio vs. ASCA 250:1 and CA 432:1 baselines on the dashboard. (Domain 10.)
8. **Summer-melt outreach workflow.** July–August reminder cadence for college-intending seniors. (Domain 5.)
9. **Structured BTAM intake + CANRA timer + AB 2657 export.** (Domain 11.)
10. **Annual Student Outcome Goal dashboard** at the program level (not just per-student goals) to close the ASCA Define→Manage→Assess loop. (Domain 1.)

Items 1–5 would each move the needle for a real counselor's day; items 6–10 are higher-effort but strongly aligned with what the literature says matters.
