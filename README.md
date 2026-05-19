# Counselor Assistant

**An all-in-one, 100% local school counselor management tool.**
No cloud. No uploads. No subscriptions. FERPA & ASCA compliant by design.

Built by a school counselor, for school counselors. Inspired by [SCUTA](https://www.myscuta.com/) with expanded tools for caseload management, scheduling, communication, analytics, and course catalog management.

---

## Why Counselor Assistant?

Most school counselor tools are cloud-based, expensive, and raise FERPA concerns. Counselor Assistant runs entirely on your computer -- your student data never leaves your machine. It's free, open-source, and built around the ASCA National Model.

**The Trident Framework:**

| Pillar | Tools |
|--------|-------|
| **Executive Assistant** | Dashboard, Smart Alerts, Calendar, Scheduling, Follow-Ups |
| **Operations** | Caseload, Notes, Goals, Referrals, Groups, MTSS/RTI, Screeners, IEP/504, Consents, Documents, Service Log |
| **Marketing & Data** | Analytics, Reports, Activity Log, Communication Log/Drafts, Mail Merge, Knowledge Base, AI Tools |

---

## Features

### Daily Workflow
| Module | Description |
|--------|-------------|
| **Dashboard** | Daily overview: critical alerts, today's schedule, follow-ups due, weekly activity totals, charts |
| **Caseload** | Full student profiles, demographics, IEP/504/EL flags, tagging, search & filter, paginated |
| **Calendar** | Daily/weekly/monthly views, optional Google Calendar sync via OAuth |
| **Conference Notes** | Confidential session notes (Flow / Structured / Cornell / Outline formats), ASCA domain alignment, follow-up tracking, paginated |
| **Follow-Ups** | Single inbox for everything that needs follow-up across notes, referrals, and interventions |

### Student Services
| Module | Description |
|--------|-------------|
| **Goals** | Per-student SMART goals with progress percent and target dates |
| **Counseling Groups** | Group rosters with shared session notes |
| **Referrals** | Outside-service intake/route tracking with status pipeline |
| **MTSS / RTI** | Tier 1/2/3 intervention plans with progress notes and review reminders |
| **Screeners** | ACEs, RIASEC, equity-focused, career & personality assessments (optional Google Forms + Classroom integration) |
| **IEP / 504** | Plan tracking, accommodations, review-date alerts, optional PDF parsing via local AI |
| **Consents** | Parental consent forms with expiration tracking |
| **Student Documents** | Per-student file uploads (PDF, Office, images) — counselor-scoped, never shared |

### Academics
| Module | Description |
|--------|-------------|
| **Academic Plan** | 4-year course planner with optional AI auto-fill |
| **Graduation** | At-risk roster from transcript imports — credit shortfall, a-g status, CTE pathway tracking (District 2-course model + federal Perkins V status side-by-side) |
| **College & Career** | Pathway, GPA, test scores, application tracking, FAFSA status |
| **Course Catalog** | Department-organized courses with prerequisites, grad requirements, NCAA status |
| **Post-Grad** | Outcome tracking (college, military, workforce, gap year) |

### Meetings & Communication
| Module | Description |
|--------|-------------|
| **Meeting Notes** | Multi-student meetings with @mentions; optional audio recording + local transcription + AI summary (faster-whisper) |
| **Meeting Prep** | Pre-meeting student summaries with key data points |
| **Communication Log** | Phone/email/parent-contact log per student, paginated |
| **Communication Drafts** | Email templates, Google Classroom posts, newsletters, quick messages |
| **Mail Merge** | Bulk personalized letters (e.g., graduation risk letters) from caseload data |

### Reports & Analytics
| Module | Description |
|--------|-------------|
| **Analytics Dashboard** | Interactive charts: caseload demographics, academics, attendance, services, activities |
| **ELPAC Analytics** | English Learner dashboard with Overall PL distribution, domain weakness, reclassification pipeline, **Reclassification Candidates** (students at PL 4 not yet RFEP, with newly-at-4 flagged), **ELPI Status** (both simplified PL-1-4 and full CDE rubric with L/H sublevels), and a **Big Movers** table of students who changed 2+ levels in either direction |
| **Use-of-Time Report** | ASCA service-type breakdown |
| **Student Services Report** | Per-student touch counts and topics |
| **Activity Summary** | Time-on-task across categories |
| **Caseload Demographics** | Grade, gender, ethnicity, EL/IEP/504 distributions |
| **Topic Delivery** | Coverage by ASCA domain and topic |
| **Early Warning** | Students flagged by attendance / grades / referrals |
| **Cohort Trends** | Multi-year cohort tracking |
| **ASCA Results** | Process / perception / outcome data per program |
| **Closing the Gap** | Sub-group disparity tracking |
| **Equity Report** | Service distribution by demographic group |
| **Program Evaluation** | Self-assessment against ASCA program standards |
| **Activity Log** | ASCA-aligned time tracking across 4 service types and 250+ categories |

### More
| Module | Description |
|--------|-------------|
| **AI Tools Hub** | 14 counselor-focused AI generators (crisis scripts, parent comms, college, documentation) plus AI Course Recommendations on each student profile — all run locally via Ollama |
| **Student Portal** | Public token-gated AI tools for students (no login, shareable link). Essay coaching, study planning, career exploration |
| **Scheduling** | Public booking pages for parents/students, availability slots, conflict detection |
| **Knowledge Base** | District documents indexed for local RAG against AI Tools |
| **Data Import** | CSV/Excel/Synergy upload for attendance, grades, and bulk student-info updates |
| **Glossary** | ASCA-aligned counseling terms reference |
| **Smart Alerts** | Daily action items: overdue follow-ups, IEP reviews, attendance flags, failing grades, new students |

---

## Getting Started

### Try the Demo First

Want to click around before committing? Run in demo mode and a fully-seeded caseload of 25 fake students (with notes, grades, ELPAC scores, transcripts, IEP/504 plans, calendar events, and goals) loads automatically — no setup wizard, no account creation. Hit "Reset Demo" any time to start over.

```bash
COUNSELOR_DEMO=1 python run.py        # Mac/Linux
set COUNSELOR_DEMO=1 && python run.py  # Windows
```

Browser opens to a pre-authenticated counselor account. Edit, delete, break things on purpose — your real data isn't touched.

### Option 1: Standard Install (Recommended)

**Requirements:** Python 3.9 or newer

```bash
# 1. Download the project
git clone <your-fork-url>
cd Counselor-Assistant

# 2. (Recommended) Create a virtual environment
python -m venv venv

# On Mac/Linux:
source venv/bin/activate

# On Windows:
venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Launch
python run.py
```

Open your browser to **http://127.0.0.1:5000** -- the setup wizard will guide you through initial configuration.

> **Helper scripts:** `install.sh` (Mac/Linux) and `install.bat` (Windows) automate steps 2-3 if you'd rather not run them manually. `start.bat`, `backup.bat`, and `restore.bat` are also included for day-to-day use on Windows.

### Option 2: USB-Distributable Demo Bundle (No Python Required on Target Machine)

For school computers that block Python installs, conference demos, or anyone who wants to drop the app on a flash drive and double-click. The bundle ships per-platform Python runtimes (Windows, Mac Apple Silicon, Linux x86_64) plus prebuilt wheels — no admin rights, no install, no internet on the target machine.

```bash
# On a build machine with internet access:
python3 scripts/build_usb_bundle.py --output dist/usb-bundle --clean
```

Copy the resulting `dist/usb-bundle/` onto an exFAT-formatted USB stick. End users see:

```
USB-stick/
├── START_HERE_Windows.bat       ← double-click on Windows
├── START_HERE_Mac.command       ← double-click on Mac
├── START_HERE_Linux.sh          ← double-click on Linux
├── README_FIRST.txt
├── runtimes/{windows,macos,linux}/
└── Counselor-Assistant/
```

The launcher sets `COUNSELOR_DEMO=1` and writes any test data to `~/CounselorAssistantDemo/` so the user can delete one folder to wipe everything. See `scripts/build_usb_bundle.py` for build options (`--skip-runtimes` for fast iteration on the launcher scripts and README without re-downloading Python tarballs).

### Option 3: iPhone access via Tailscale

Want to view your dashboard on your phone during the day? Install [Tailscale](https://tailscale.com/) on both your work computer and phone (free for personal use). When `python run.py` detects Tailscale, it binds to your tailnet only -- the school LAN can't see the port. The startup banner prints the URL to type on your phone. See [`TAILSCALE_SETUP.md`](TAILSCALE_SETUP.md) for the full walkthrough.

---

## First-Run Setup

When you launch for the first time, a 7-step wizard walks you through:

1. **Welcome** -- What the app does and what you'll need
2. **Profile** -- Your name, school name, username, password
3. **Identity** -- School colors, logo, mascot (optional)
4. **Year** -- School year start/end dates, grade levels you serve
5. **Import** -- Upload a CSV to populate your caseload (or skip)
6. **Connect** -- Optional Google Calendar / Ollama / Tailscale links
7. **Finish** -- Review and start using the app

Every step is skippable. You can change all settings later under **Settings**.

---

## FERPA & Security

- All data stored in a local SQLite database (`data/counselor.db`)
- No network requests except optional Google Calendar / Forms / Classroom integration (your FERPA-covered Google Workspace)
- Session auto-timeout after 30 minutes of inactivity
- Complete audit trail of all data access (view, create, update, delete, export)
- Password-protected login with hashed passwords (Werkzeug `generate_password_hash` -- scrypt by default)
- CSRF protection on all state-changing forms
- Per-resource ownership checks on notes and documents (cross-user access returns 403)
- Optional: Ollama AI assistant runs 100% locally (no data sent to cloud)
- **Factory Reset** -- Settings → Danger Zone → Reset App wipes the database, uploads, and your account in one click (requires typing `RESET` to confirm)

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3, Flask, SQLAlchemy |
| **Database** | SQLite (local file, zero configuration, auto-migrating) |
| **Frontend** | HTML5, CSS3, vanilla JavaScript, Jinja2 templates |
| **Charts** | Chart.js 4.x (CDN) |
| **Calendar** | FullCalendar 6.x (CDN) |
| **Excel I/O** | openpyxl |
| **PDF parsing** | PyPDF2 (transcript review, knowledge-base ingestion with encrypted-PDF tolerance) |
| **Audio transcription** | faster-whisper (optional, runs locally) |
| **Optional AI** | Ollama (local LLM via HTTP) |
| **Optional Google APIs** | Calendar, Forms, Classroom (OAuth 2.0) |
| **Optional networking** | Tailscale (auto-detected at startup) |
| **Progressive Web App** | Manifest + service worker (installable on phones) |
| **Themes** | Light, Dark, School (custom colors), Focus, Auto (system) + reduced-motion option |
| **USB distribution** | python-build-standalone runtimes + prebuilt wheel cache, packaged by `scripts/build_usb_bundle.py` |

---

## Data & Backups

All data lives in the `data/` directory:

| File | Purpose |
|------|---------|
| `data/counselor.db` | Main database |
| `data/backups/` | Local backup snapshots |
| `data/uploads/` | Student documents, school logos, etc. |
| `data/.secret_key` | Session encryption key (auto-generated) |
| `data/google_credentials.json` | Optional, for Google integrations |
| `data/ollama_settings.json` | Optional, for local AI base URL + model |

**Creating backups:** Settings → Backups → Create Backup

**Transferring data:** Settings → Export / Import Data creates a portable JSON file you can save to a USB or shared drive and import on another machine.

> **Important:** The `data/` directory is gitignored. Your student data is never committed to version control.

---

## Project Structure

```
Counselor-Assistant/
├── run.py                  # Entry point (auto-detects Tailscale, COUNSELOR_DEMO mode)
├── config.py               # Configuration
├── requirements.txt        # Full dependencies (including faster-whisper, Google APIs)
├── requirements-demo.txt   # Slim subset for the USB bundle
├── install.sh / install.bat / start.bat / backup.bat / restore.bat
├── TAILSCALE_SETUP.md      # iPhone-via-Tailscale walkthrough
├── scripts/
│   ├── build_usb_bundle.py # Builds the double-clickable USB demo bundle
│   └── seed_demo.py        # Re-runs the demo seed against a fresh database
├── app/
│   ├── __init__.py         # App factory + auto-migration + demo bootstrap
│   ├── models/             # SQLAlchemy models (~30: students, notes, goals,
│   │                       #   referrals, interventions, screeners, courses,
│   │                       #   transcripts, ELPAC scores, documents, …)
│   ├── routes/             # Blueprint routes by domain (44 modules +
│   │                       #   data_import sub-package)
│   ├── templates/          # Jinja2 templates organized per blueprint
│   ├── static/             # CSS, JS (incl. shared sse-stream.js), icons,
│   │                       #   PWA manifest, service worker
│   └── utils/              # Alert engine, audit, demo seed, CTE/ELPI
│                           #   computation, Google clients, Ollama client,
│                           #   Excel helpers, caseload helpers
└── data/
    ├── demo-seed.json      # Canonical 25-student demo fixture (committed)
    └── (counselor.db, uploads/, backups/ — gitignored runtime data)
```

---

## Updating

```bash
cd Counselor-Assistant
git pull
pip install -r requirements.txt
python run.py
```

The app automatically migrates your database when new columns are added -- no manual steps needed. Always create a backup (Settings → Backups → Create Backup) before pulling a major update.

---

## FAQ

**Q: Can multiple counselors use this at the same school?**
A: Single-user per machine is the default. There's also an admin role (`/admin`) for shops that want one shared install with multiple counselor accounts on the same machine. Each counselor only sees their own caseload, notes, and documents -- the cross-user authorization is enforced at the route level. For multi-machine sync, use Settings → Export / Import Data.

**Q: Will I lose my data when I update?**
A: No. Your data lives in `data/counselor.db` which is separate from the application code. Updates only change the app files. Always make a backup before major updates, just in case.

**Q: Can I use this on a Chromebook?**
A: Not directly, since Chromebooks can't run Python natively. However, if your Chromebook supports Linux (Crostini), you can install Python and run it there.

**Q: Is the Google Calendar integration required?**
A: No. It's completely optional. The app works fully offline. Google Calendar / Forms / Classroom add sync, screener delivery, and public booking pages if your school's Google Workspace is available.

**Q: How do I view this on my phone?**
A: Install Tailscale on both your work computer and phone, sign in to the same account, and run `python run.py`. The startup banner will print the URL to type on your phone. See [`TAILSCALE_SETUP.md`](TAILSCALE_SETUP.md).

**Q: How do I start over from scratch?**
A: Settings → Danger Zone → Reset App. Type `RESET` to confirm. All data is deleted and you go back through the setup wizard. Make a backup first if you might want this data back.

---

## Contributing

This project is in active development. If you're a school counselor with feature ideas, or a developer who wants to contribute, open an issue or pull request.

---

## License

[MIT](LICENSE) — free to use, modify, and distribute. See the `LICENSE` file for the full text.
