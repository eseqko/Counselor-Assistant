from flask import Blueprint, redirect, url_for
from flask_login import login_required

service_log_bp = Blueprint('service_log', __name__)


@service_log_bp.route('/')
@login_required
def index():
    return redirect(url_for('notes.index'))


@service_log_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_record():
    return redirect(url_for('notes.add_note'))


@service_log_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_record(id):
    return redirect(url_for('notes.index'))


@service_log_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete_record(id):
    return redirect(url_for('notes.index'))
