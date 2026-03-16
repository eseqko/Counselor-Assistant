# Counselor Assistant

An all-in-one, **100% local** school counselor management tool. No cloud. No uploads. FERPA & ASCA compliant.

Inspired by [SCUTA](https://www.myscuta.com/) with additional tools for course catalog management and comprehensive caseload tracking.

## Features

| Module | Description |
|--------|-------------|
| **Dashboard** | Daily overview, quick stats, use-of-time bar, follow-up reminders, quick actions |
| **Caseload Manager** | Full student profiles, demographics, IEP/504/ELL flags, tagging, search & filter |
| **Counselor Notes** | Confidential session notes per student, ASCA domain alignment, follow-up tracking |
| **Student Service Log** | Chronological service records per student with outcome tracking and referrals |
| **Calendar** | Interactive calendar (FullCalendar) with daily/weekly/monthly views, event types, student linking |
| **Activity Log** | ASCA-aligned time tracking across 4 service types with 250+ categories |
| **Reports** | Use-of-Time Analysis, Student Services Report, Activity Summary, Caseload Demographics, Topic Delivery Log |
| **Course Catalog Wiki** | Complete course catalog with departments, prerequisites, grad requirements, NCAA status, counselor notes |
| **Glossary** | ASCA-aligned counseling terms glossary with categories and seeding |
| **Settings** | Profile management, password changes, local backups, FERPA audit log |

## FERPA & ASCA Compliance

- All data stored in a local SQLite database (`data/counselor.db`)
- No network requests except for the calendar UI library (FullCalendar CDN)
- Session auto-timeout after 30 minutes of inactivity
- Complete audit trail of all data access (view, create, update, delete, export)
- Password-protected login with hashed passwords
- CSRF protection on all forms
- Print-friendly reports for documentation

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python run.py

# Open browser to http://127.0.0.1:5000
# Default login: counselor / changeme
```

## Tech Stack

- **Backend:** Python 3, Flask, SQLAlchemy
- **Database:** SQLite (local file)
- **Frontend:** HTML5, CSS3, vanilla JavaScript
- **Calendar:** FullCalendar 6.x

## Data & Backups

All data lives in the `data/` directory:
- `data/counselor.db` - Main database
- `data/backups/` - Local backups
- `data/.secret_key` - Session encryption key

Create backups from Settings > Data Management. Backups are local `.db` files you can copy to a USB drive or external storage.

## Project Structure

```
Counselor-Assistant/
├── run.py                  # Entry point
├── config.py               # Configuration
├── requirements.txt        # Python dependencies
├── app/
│   ├── __init__.py         # App factory
│   ├── models/             # Database models
│   │   ├── user.py         # Users & audit logs
│   │   ├── student.py      # Students & tags
│   │   ├── note.py         # Counselor notes
│   │   ├── activity.py     # Activity log
│   │   ├── calendar_event.py
│   │   ├── service_record.py
│   │   ├── course.py       # Course catalog & grad reqs
│   │   └── glossary_term.py
│   ├── routes/             # Blueprint routes
│   │   ├── auth.py
│   │   ├── dashboard.py
│   │   ├── caseload.py
│   │   ├── calendar.py
│   │   ├── notes.py
│   │   ├── activity_log.py
│   │   ├── service_log.py
│   │   ├── reports.py
│   │   ├── course_catalog.py
│   │   ├── glossary.py
│   │   └── settings.py
│   ├── templates/          # Jinja2 HTML templates
│   ├── static/             # CSS & JS
│   └── utils/              # Helpers & audit logging
└── data/                   # Local database (gitignored)
```
