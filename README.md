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
| **Executive Assistant** | Dashboard, Smart Alerts, Calendar, Scheduling, Task Automation |
| **Operations** | Caseload Manager, Notes, Service Log, Activity Log, IEP/504 Tracking |
| **Marketing & Data** | Analytics Dashboard, Reports, Communication Drafts |

---

## Features

### Core Modules
| Module | Description |
|--------|-------------|
| **Dashboard** | Daily overview with smart alerts, action items, quick stats, follow-up reminders |
| **Caseload Manager** | Full student profiles, demographics, IEP/504/ELL flags, tagging, search & filter |
| **Counselor Notes** | Confidential session notes, ASCA domain alignment, follow-up tracking |
| **Student Service Log** | Chronological service records with outcome tracking and referrals |
| **Calendar** | Interactive calendar with daily/weekly/monthly views, Google Calendar integration |
| **Scheduling** | Public booking pages for parents/students, availability management, conflict detection |
| **Activity Log** | ASCA-aligned time tracking across 4 service types with 250+ categories |

### Data & Analytics
| Module | Description |
|--------|-------------|
| **Analytics Dashboard** | 14 interactive charts: caseload demographics, academics, attendance, services, activities |
| **Reports** | Use-of-Time, Student Services, Activity Summary, Caseload Demographics, Topic Delivery |
| **Communication Drafts** | Email templates, Google Classroom posts, newsletters, quick messages |

### Additional Tools
| Module | Description |
|--------|-------------|
| **IEP/504 Tracker** | Review dates, compliance monitoring, document tracking |
| **Course Catalog Wiki** | Complete course catalog with prerequisites, grad requirements, NCAA status |
| **Meeting Prep** | Pre-meeting student summaries with key data points |
| **Glossary** | ASCA-aligned counseling terms glossary |
| **Smart Alerts** | Daily action items: overdue follow-ups, IEP reviews, attendance flags, new students |

---

## Getting Started

### Option 1: Standard Install (Recommended)

**Requirements:** Python 3.9 or newer

```bash
# 1. Download the project
git clone https://github.com/YOUR-USERNAME/Counselor-Assistant.git
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

### Option 2: Portable USB Install (No Admin Rights Needed)

For school computers where you can't install software:

1. **On your home computer**, install [WinPython](https://winpython.github.io/) (portable Python) to a USB drive
2. Copy the `Counselor-Assistant` folder to the same USB drive
3. Create a `start.bat` file on the USB drive:

```bat
@echo off
echo Starting Counselor Assistant...
cd /d "%~dp0Counselor-Assistant"
"%~dp0python-3.x.x\python.exe" -m pip install -r requirements.txt --quiet
"%~dp0python-3.x.x\python.exe" run.py
pause
```

4. Double-click `start.bat` on any Windows computer -- no installation required

> **Tip:** Replace `python-3.x.x` with the actual folder name from WinPython (e.g., `python-3.12.4.amd64`).

---

## First-Run Setup

When you launch for the first time, a setup wizard walks you through:

1. **Your Profile** -- Name, school name, username, password
2. **School Configuration** -- School year dates, grade levels you serve
3. **Import Students** -- Upload a CSV to populate your caseload (or skip for later)

Every step is skippable. You can always change these settings later.

---

## FERPA & Security

- All data stored in a local SQLite database (`data/counselor.db`)
- No network requests except optional Google Calendar integration (your FERPA-covered Google Workspace)
- Session auto-timeout after 30 minutes of inactivity
- Complete audit trail of all data access (view, create, update, delete, export)
- Password-protected login with hashed passwords (Werkzeug/bcrypt)
- CSRF protection on all forms
- Optional: Ollama AI assistant runs 100% locally (no data sent to cloud)

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3, Flask, SQLAlchemy |
| **Database** | SQLite (local file, zero configuration) |
| **Frontend** | HTML5, CSS3, vanilla JavaScript |
| **Charts** | Chart.js 4.x (CDN) |
| **Calendar** | FullCalendar 6.x (CDN) |
| **Optional** | Google Calendar API (OAuth 2.0), Ollama (local AI) |

---

## Data & Backups

All data lives in the `data/` directory:

| File | Purpose |
|------|---------|
| `data/counselor.db` | Main database |
| `data/backups/` | Local backup snapshots |
| `data/.secret_key` | Session encryption key (auto-generated) |

**Creating backups:** Settings > Data Management > Create Backup

**Transferring data:** Settings > Export Data creates a portable JSON file you can import on another machine.

> **Important:** The `data/` directory is gitignored. Your student data is never committed to version control.

---

## Project Structure

```
Counselor-Assistant/
├── run.py                  # Entry point
├── config.py               # Configuration
├── requirements.txt        # Python dependencies
├── app/
│   ├── __init__.py         # App factory + auto-migration
│   ├── models/             # Database models
│   │   ├── user.py         # Users, audit logs
│   │   ├── student.py      # Students, tags
│   │   ├── note.py         # Counselor notes
│   │   ├── activity.py     # Activity log entries
│   │   ├── calendar_event.py
│   │   ├── service_record.py
│   │   ├── course.py       # Course catalog, grad reqs
│   │   ├── attendance.py   # Attendance records
│   │   ├── grade.py        # Grade records
│   │   ├── iep504.py       # IEP/504 plans
│   │   ├── availability.py # Scheduling slots, bookings
│   │   └── glossary_term.py
│   ├── routes/             # Blueprint routes (22 modules)
│   ├── templates/          # Jinja2 HTML templates
│   ├── static/             # CSS, JS, images
│   └── utils/              # Helpers, alert engine, Google API
└── data/                   # Local database (gitignored)
```

---

## Updating

```bash
cd Counselor-Assistant
git pull
pip install -r requirements.txt
python run.py
```

The app automatically migrates your database when new columns are added -- no manual steps needed.

---

## FAQ

**Q: Can multiple counselors use this at the same school?**
A: Currently it's designed for single-user use. Each counselor runs their own instance. Multi-user support (shared server) is on the roadmap.

**Q: Will I lose my data when I update?**
A: No. Your data lives in `data/counselor.db` which is separate from the application code. Updates only change the app files. Always make a backup before major updates, just in case.

**Q: Can I use this on a Chromebook?**
A: Not directly, since Chromebooks can't run Python natively. However, if your Chromebook supports Linux (Crostini), you can install Python and run it there.

**Q: Is the Google Calendar integration required?**
A: No. It's completely optional. The app works fully offline. Google Calendar adds sync and public booking pages if your school's Google Workspace is available.

---

## Contributing

This project is in active development. If you're a school counselor with feature ideas, or a developer who wants to contribute, open an issue or pull request.

---

## License

This project is open source. Built with care for the counseling community.
