"""First-run setup wizard. Guides new users through initial configuration."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_user, current_user
from app import db, csrf
from app.models.user import User
from app.utils.audit import log_action
import json, csv, io

setup_bp = Blueprint('setup', __name__, template_folder='../templates/setup')


def needs_setup():
    """Check if the app needs first-run setup."""
    user = User.query.first()
    return user is None or not user.setup_completed


@setup_bp.route('/setup', methods=['GET', 'POST'])
def index():
    """Multi-step setup wizard."""
    # If setup already done, go to dashboard
    if not needs_setup() and current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        step = request.form.get('step', '')

        if step == 'complete':
            return _handle_complete(request.form)

    return render_template('setup/wizard.html')


def _handle_complete(form):
    """Process the full setup form submission."""
    # Get or create user
    user = User.query.first()
    if not user:
        user = User(username='counselor', display_name='School Counselor', role='counselor')
        user.set_password('changeme')
        db.session.add(user)
        db.session.flush()

    # Step 1: Profile
    display_name = form.get('display_name', '').strip()
    if display_name:
        user.display_name = display_name

    school_name = form.get('school_name', '').strip()
    if school_name:
        user.school_name = school_name

    username = form.get('username', '').strip()
    if username and len(username) >= 3:
        # Only change if not taken
        existing = User.query.filter_by(username=username).first()
        if not existing or existing.id == user.id:
            user.username = username

    password = form.get('password', '')
    if password and len(password) >= 8:
        user.set_password(password)

    # Step 2: School config
    school_config = {}
    school_year_start = form.get('school_year_start', '').strip()
    school_year_end = form.get('school_year_end', '').strip()
    if school_year_start:
        school_config['school_year_start'] = school_year_start
    if school_year_end:
        school_config['school_year_end'] = school_year_end

    grade_levels = form.getlist('grade_levels')
    if grade_levels:
        school_config['grade_levels'] = grade_levels

    counselor_title = form.get('counselor_title', '').strip()
    if counselor_title:
        school_config['counselor_title'] = counselor_title

    if school_config:
        # Merge with existing config if any
        existing_config = {}
        if user.school_config_json:
            try:
                existing_config = json.loads(user.school_config_json)
            except (json.JSONDecodeError, TypeError):
                pass
        existing_config.update(school_config)
        user.school_config_json = json.dumps(existing_config)

    # Mark setup as complete
    user.setup_completed = True
    db.session.commit()

    # Log the user in
    login_user(user, remember=False)
    log_action('setup_complete', 'user', user.id)

    flash('Setup complete! Welcome to Counselor Assistant.', 'success')
    return redirect(url_for('dashboard.index'))


@setup_bp.route('/setup/import-preview', methods=['POST'])
@csrf.exempt
def import_preview():
    """Preview CSV headers for column mapping. Returns JSON."""
    file = request.files.get('file')
    if not file or not file.filename:
        return {'ok': False, 'error': 'No file selected'}, 400

    fname = file.filename.lower()
    try:
        if fname.endswith('.csv'):
            content = file.read().decode('utf-8-sig')
            reader = csv.reader(io.StringIO(content))
            headers = next(reader)
            # Count rows
            row_count = sum(1 for _ in reader)
        elif fname.endswith(('.xlsx', '.xls')):
            from openpyxl import load_workbook
            wb = load_workbook(file, data_only=True, read_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                return {'ok': False, 'error': 'Empty file'}, 400
            headers = [str(c) if c else '' for c in rows[0]]
            row_count = len(rows) - 1
            wb.close()
        else:
            return {'ok': False, 'error': 'Please upload a CSV or Excel file'}, 400

        headers = [h.strip() for h in headers if h.strip()]
        return {'ok': True, 'headers': headers, 'row_count': row_count}
    except Exception as e:
        return {'ok': False, 'error': str(e)}, 400
