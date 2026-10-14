"""Inventory overview, stock adjustments and movement history."""
from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy import or_

from extensions import db
from models import Product, StockMovement
from routes.decorators import admin_required
from services import audit_service, inventory_service
from services.inventory_service import InventoryError
from utils import ValidationError, parse_int, parse_optional_id

inventory_bp = Blueprint("inventory", __name__)


@inventory_bp.route("/")
@admin_required
def index():
    q = (request.args.get("q") or "").strip()
    stock = request.args.get("stock", "all")
    page = parse_int(request.args.get("page"), "page", minimum=1, required=False, default=1)

    query = Product.query
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Product.name.ilike(like), Product.sku.ilike(like)))
    if stock == "low":
        query = query.filter(Product.stock_quantity > 0, Product.stock_quantity <= Product.low_stock_threshold)
    elif stock == "out":
        query = query.filter(Product.stock_quantity <= 0)

    query = query.order_by(
        (Product.stock_quantity <= 0).desc(),
        (Product.stock_quantity <= Product.low_stock_threshold).desc(),
        Product.stock_quantity.asc(),
    )
    pagination = query.paginate(page=page, per_page=20, error_out=False)
    return render_template(
        "inventory.html",
        pagination=pagination,
        products=pagination.items,
        q=q,
        stock=stock,
        summary=inventory_service.counts(),
        stock_value=inventory_service.total_stock_value(),
    )


@inventory_bp.route("/<int:product_id>/adjust", methods=["POST"])
@admin_required
def adjust(product_id):
    product = db.session.get(Product, product_id)
    if product is None:
        abort(404)
    try:
        change = parse_int(request.form.get("quantity_change"), "Quantity change", required=True)
        if change == 0:
            raise ValidationError("Quantity change cannot be zero.")
        reason = (request.form.get("reason") or "").strip()
        if not reason:
            raise ValidationError("A reason is required for manual stock adjustments.")
        movement_type = "adjustment" if change < 0 else "purchase"
        inventory_service.adjust_stock(
            product,
            change,
            movement_type=movement_type,
            reason=reason,
            user_id=_user_id(),
        )
        audit_service.log_action(
            "inventory.adjust", "Product", product.id, details=f"{change:+d} ({reason})"
        )
        db.session.commit()
        flash(f"Stock for '{product.name}' updated by {change:+d}.", "success")
    except (ValidationError, InventoryError) as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(request.referrer or url_for("inventory.index"))


def _user_id():
    from flask_login import current_user

    return current_user.id if current_user and current_user.is_authenticated else None


@inventory_bp.route("/movements")
@admin_required
def movements():
    page = parse_int(request.args.get("page"), "page", minimum=1, required=False, default=1)
    product_id = parse_optional_id(request.args.get("product"))
    movement_type = request.args.get("type") or ""

    query = StockMovement.query
    if product_id:
        query = query.filter(StockMovement.product_id == product_id)
    if movement_type:
        query = query.filter(StockMovement.movement_type == movement_type)
    query = query.order_by(StockMovement.created_at.desc())
    pagination = query.paginate(page=page, per_page=25, error_out=False)
    return render_template(
        "movements.html",
        pagination=pagination,
        movements=pagination.items,
        products=Product.query.order_by(Product.name.asc()).all(),
        product_id=product_id,
        movement_type=movement_type,
    )
