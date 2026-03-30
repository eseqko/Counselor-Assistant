"""Alert API routes — powers the dashboard panel and notification bell."""
from flask import Blueprint, jsonify
from flask_login import login_required, current_user
from app import csrf
from app.utils.alert_engine import get_alerts, refresh_alerts, get_alert_count

alerts_bp = Blueprint('alerts', __name__)


@alerts_bp.route('/api/alerts')
@login_required
def api_get_alerts():
    """Return all alerts for the current user (generates if needed)."""
    alerts = get_alerts(current_user)
    return jsonify({
        'ok': True,
        'alerts': alerts,
        'count': len(alerts),
    })


@alerts_bp.route('/api/alerts/count')
@login_required
def api_alert_count():
    """Quick count for the notification badge."""
    count = get_alert_count(current_user)
    return jsonify({'count': count})


@alerts_bp.route('/api/alerts/refresh', methods=['POST'])
@csrf.exempt
@login_required
def api_refresh_alerts():
    """Force-regenerate alerts (after data changes)."""
    alerts = refresh_alerts(current_user)
    return jsonify({
        'ok': True,
        'alerts': alerts,
        'count': len(alerts),
    })
