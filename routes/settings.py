"""Store settings and audit log (admin only)."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from extensions import db
from models import AuditLog
from routes.decorators import admin_required
from services import audit_service
from services.settings_service import (
    EDITABLE_KEYS,
    LABELS,
    all_settings,
    set_setting,
)
from utils import ValidationError, parse_decimal, parse_int

settings_bp = Blueprint("settings", __name__)

INT_KEYS = {"DEFAULT_LOW_STOCK_THRESHOLD"}
PERCENT_KEYS = {"DEFAULT_TAX_RATE", "MAX_BILL_DISCOUNT_PERCENT"}


@settings_bp.route("/", methods=["GET", "POST"])
@admin_required
def index():
    if request.method == "POST":
        try:
            values = {}
            for key in EDITABLE_KEYS:
                raw = (request.form.get(key) or "").strip()
                if key in INT_KEYS:
                    raw = str(parse_int(raw, LABELS.get(key, key), minimum=0))
                elif key in PERCENT_KEYS:
                    raw = str(parse_decimal(raw, LABELS.get(key, key), minimum=0, maximum=100))
                values[key] = raw
            for key, value in values.items():
                set_setting(key, value)
            audit_service.log_action("settings.update", "Setting", None, details="store settings updated")
            db.session.commit()
            flash("Settings saved.", "success")
            return redirect(url_for("settings.index"))
        except ValidationError as exc:
            db.session.rollback()
            flash(str(exc), "danger")

    return render_template("settings.html", settings=all_settings(), labels=LABELS, keys=EDITABLE_KEYS)


@settings_bp.route("/audit")
@admin_required
def audit():
    page = request.args.get("page", 1, type=int)
    pagination = AuditLog.query.order_by(AuditLog.created_at.desc()).paginate(
        page=page, per_page=30, error_out=False
    )
    return render_template("audit.html", pagination=pagination, logs=pagination.items)
