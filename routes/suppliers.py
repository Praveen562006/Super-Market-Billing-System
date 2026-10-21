"""Supplier directory (admin only).

Suppliers are kept as a standalone contact book: name, contact person, phone,
email, address and tax number.  Products are not linked yet, so a supplier can
be added and maintained without touching the catalogue.
"""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import or_

from extensions import db
from models import Supplier
from routes.decorators import admin_required
from services import audit_service
from utils import ValidationError, clean_str

suppliers_bp = Blueprint("suppliers", __name__)


def _validate(form):
    name = clean_str(form.get("name"), 160)
    if not name:
        raise ValidationError("Supplier name is required.")
    return {
        "name": name,
        "contact_person": clean_str(form.get("contact_person"), 120) or None,
        "phone": clean_str(form.get("phone"), 30) or None,
        "email": clean_str(form.get("email"), 160) or None,
        "address": clean_str(form.get("address"), 255) or None,
        "gstin": clean_str(form.get("gstin"), 40) or None,
        "notes": clean_str(form.get("notes"), 2000) or None,
        "is_active": form.get("is_active") in ("on", "1"),
    }


@suppliers_bp.route("/")
@admin_required
def index():
    q = (request.args.get("q") or "").strip()
    status = request.args.get("status", "active")

    query = Supplier.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Supplier.name.ilike(like),
                Supplier.contact_person.ilike(like),
                Supplier.phone.ilike(like),
                Supplier.email.ilike(like),
            )
        )
    if status == "active":
        query = query.filter(Supplier.is_active.is_(True))
    elif status == "inactive":
        query = query.filter(Supplier.is_active.is_(False))

    suppliers = query.order_by(Supplier.name.asc()).all()
    return render_template("suppliers.html", suppliers=suppliers, q=q, status=status)


@suppliers_bp.route("/new", methods=["GET", "POST"])
@admin_required
def create():
    if request.method == "POST":
        try:
            data = _validate(request.form)
            supplier = Supplier(**data)
            db.session.add(supplier)
            db.session.flush()
            audit_service.log_action("supplier.create", "Supplier", supplier.id, details=supplier.name)
            db.session.commit()
            flash(f"Supplier '{supplier.name}' added.", "success")
            return redirect(url_for("suppliers.index"))
        except ValidationError as exc:
            db.session.rollback()
            flash(str(exc), "danger")

    return render_template("supplier_form.html", supplier=None)


@suppliers_bp.route("/<int:supplier_id>/edit", methods=["GET", "POST"])
@admin_required
def edit(supplier_id):
    supplier = db.session.get(Supplier, supplier_id)
    if supplier is None:
        abort(404)

    if request.method == "POST":
        try:
            data = _validate(request.form)
            for key, value in data.items():
                setattr(supplier, key, value)
            audit_service.log_action("supplier.update", "Supplier", supplier.id, details=supplier.name)
            db.session.commit()
            flash(f"Supplier '{supplier.name}' updated.", "success")
            return redirect(url_for("suppliers.index"))
        except ValidationError as exc:
            db.session.rollback()
            flash(str(exc), "danger")

    return render_template("supplier_form.html", supplier=supplier)


@suppliers_bp.route("/<int:supplier_id>/toggle", methods=["POST"])
@admin_required
def toggle(supplier_id):
    supplier = db.session.get(Supplier, supplier_id)
    if supplier is None:
        abort(404)
    supplier.is_active = not supplier.is_active
    audit_service.log_action(
        "supplier.activate" if supplier.is_active else "supplier.deactivate",
        "Supplier",
        supplier.id,
        details=supplier.name,
    )
    db.session.commit()
    flash(
        f"Supplier '{supplier.name}' {'activated' if supplier.is_active else 'deactivated'}.",
        "success",
    )
    return redirect(request.referrer or url_for("suppliers.index"))


@suppliers_bp.route("/<int:supplier_id>/delete", methods=["POST"])
@admin_required
def delete(supplier_id):
    supplier = db.session.get(Supplier, supplier_id)
    if supplier is None:
        abort(404)
    name = supplier.name
    db.session.delete(supplier)
    audit_service.log_action("supplier.delete", "Supplier", supplier_id, details=name)
    db.session.commit()
    flash(f"Supplier '{name}' deleted.", "success")
    return redirect(url_for("suppliers.index"))
