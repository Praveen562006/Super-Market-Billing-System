"""Admin dashboard with live statistics."""
from flask import Blueprint, render_template
from flask_login import login_required

from services import report_service

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.after_request
def prevent_dashboard_caching(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@dashboard_bp.route("/")
@dashboard_bp.route("/dashboard")
@login_required
def index():
    stats = report_service.dashboard_stats()
    return render_template("dashboard.html", stats=stats)
