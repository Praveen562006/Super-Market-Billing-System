"""Authentication: login, logout and password change."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func

from extensions import db
from models import User
from services import audit_service
from utils import utcnow

auth_bp = Blueprint("auth", __name__)


def _safe_next(target):
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return None


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        remember = bool(request.form.get("remember"))

        if not username or not password:
            flash("Username and password are required.", "danger")
            return render_template("login.html"), 400

        user = User.query.filter(func.lower(User.username) == username.lower()).first()
        if user is None or not user.check_password(password):
            audit_service.log_action(
                "auth.login_failed", entity="User", entity_id=username, commit=True
            )
            flash("Invalid username or password.", "danger")
            return render_template("login.html"), 401

        if not user.is_active:
            flash("This account has been disabled. Contact an administrator.", "warning")
            return render_template("login.html"), 403

        login_user(user, remember=remember)
        user.last_login_at = utcnow()
        audit_service.log_action("auth.login", entity="User", entity_id=user.id, commit=True)
        flash(f"Welcome back, {user.display_name()}!", "success")
        return redirect(_safe_next(request.args.get("next")) or url_for("dashboard.index"))

    return render_template("login.html")


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    audit_service.log_action("auth.logout", entity="User", entity_id=current_user.id, commit=True)
    logout_user()
    flash("You have been signed out.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current = request.form.get("current_password") or ""
        new = request.form.get("new_password") or ""
        confirm = request.form.get("confirm_password") or ""

        if not current_user.check_password(current):
            flash("Your current password is incorrect.", "danger")
        elif len(new) < 8:
            flash("The new password must be at least 8 characters.", "danger")
        elif new != confirm:
            flash("The new passwords do not match.", "danger")
        else:
            current_user.set_password(new)
            audit_service.log_action(
                "auth.password_changed", entity="User", entity_id=current_user.id
            )
            db.session.commit()
            flash("Your password has been updated.", "success")
            return redirect(url_for("dashboard.index"))

    return render_template("change_password.html")
