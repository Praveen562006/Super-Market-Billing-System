"""User administration (admin only)."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import User
from routes.decorators import admin_required
from services import audit_service
from utils import ValidationError, clean_str

users_bp = Blueprint("users", __name__)

VALID_ROLES = (User.ROLE_ADMIN, User.ROLE_CASHIER)


def _validate(form, user=None):
    username = clean_str(form.get("username"), 80)
    if not username:
        raise ValidationError("Username is required.")
    role = form.get("role", User.ROLE_CASHIER)
    if role not in VALID_ROLES:
        raise ValidationError("Invalid role selected.")
    full_name = clean_str(form.get("full_name"), 120) or None
    return username, full_name, role


@users_bp.route("/")
@admin_required
def index():
    users = User.query.order_by(User.username.asc()).all()
    return render_template("users.html", users=users)


@users_bp.route("/new", methods=["GET", "POST"])
@admin_required
def create():
    if request.method == "POST":
        try:
            username, full_name, role = _validate(request.form)
            password = request.form.get("password") or ""
            if len(password) < 8:
                raise ValidationError("Password must be at least 8 characters.")
            if User.query.filter(func_lower(username)).first():
                raise ValidationError("That username is already taken.")
            user = User(username=username, full_name=full_name, role=role, is_active=True)
            user.set_password(password)
            db.session.add(user)
            audit_service.log_action("user.create", "User", None, details=f"{username} ({role})")
            db.session.commit()
            flash(f"User '{username}' created.", "success")
            return redirect(url_for("users.index"))
        except ValidationError as exc:
            flash(str(exc), "danger")
        except IntegrityError:
            db.session.rollback()
            flash("That username is already taken.", "danger")
    return render_template("user_form.html", user=None)


@users_bp.route("/<int:user_id>/edit", methods=["GET", "POST"])
@admin_required
def edit(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    if request.method == "POST":
        try:
            username, full_name, role = _validate(request.form, user)
            existing = User.query.filter(func_lower(username), User.id != user.id).first()
            if existing:
                raise ValidationError("That username is already taken.")
            if user.is_admin and role != User.ROLE_ADMIN and _active_admin_count() <= 1:
                raise ValidationError("At least one active administrator must remain.")
            user.username = username
            user.full_name = full_name
            user.role = role
            password = request.form.get("password") or ""
            if password:
                if len(password) < 8:
                    raise ValidationError("Password must be at least 8 characters.")
                user.set_password(password)
            audit_service.log_action("user.update", "User", user.id, details=f"{username} ({role})")
            db.session.commit()
            flash(f"User '{username}' updated.", "success")
            return redirect(url_for("users.index"))
        except ValidationError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        except IntegrityError:
            db.session.rollback()
            flash("That username is already taken.", "danger")
    return render_template("user_form.html", user=user)


@users_bp.route("/<int:user_id>/toggle", methods=["POST"])
@admin_required
def toggle(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    if user.id == current_user.id:
        flash("You cannot disable your own account.", "danger")
        return redirect(url_for("users.index"))
    if user.is_active and user.is_admin and _active_admin_count() <= 1:
        flash("At least one active administrator must remain.", "danger")
        return redirect(url_for("users.index"))
    user.is_active = not user.is_active
    audit_service.log_action(
        "user.activate" if user.is_active else "user.deactivate",
        "User",
        user.id,
        details=user.username,
    )
    db.session.commit()
    flash(f"User '{user.username}' {'activated' if user.is_active else 'disabled'}.", "success")
    return redirect(url_for("users.index"))


@users_bp.route("/<int:user_id>/delete", methods=["POST"])
@admin_required
def delete(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    if user.id == current_user.id:
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for("users.index"))
    if user.sales.count() > 0:
        user.is_active = False
        audit_service.log_action("user.deactivate", "User", user.id, details=f"{user.username} (has sales)")
        db.session.commit()
        flash(f"'{user.username}' has sales history, so the account was disabled instead.", "warning")
        return redirect(url_for("users.index"))
    username = user.username
    db.session.delete(user)
    audit_service.log_action("user.delete", "User", user_id, details=username)
    db.session.commit()
    flash(f"User '{username}' deleted.", "success")
    return redirect(url_for("users.index"))


def func_lower(value):
    from sqlalchemy import func

    return func.lower(User.username) == value.lower()


def _active_admin_count():
    return User.query.filter(User.role == User.ROLE_ADMIN, User.is_active.is_(True)).count()
