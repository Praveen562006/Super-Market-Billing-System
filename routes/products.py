"""Product and category management (admin only)."""
from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import Category, Product, StockMovement
from routes.decorators import admin_required
from services import audit_service
from services.settings_service import get_default_low_stock_threshold
from utils import ValidationError, clean_str, parse_decimal, parse_int, parse_optional_id

products_bp = Blueprint("products", __name__)

SORT_COLUMNS = {
    "name": Product.name,
    "price": Product.selling_price,
    "stock": Product.stock_quantity,
    "updated": Product.updated_at,
    "created": Product.created_at,
}


@products_bp.route("/")
@admin_required
def index():
    q = (request.args.get("q") or "").strip()
    category_id = parse_optional_id(request.args.get("category"))
    status = request.args.get("status", "active")
    stock = request.args.get("stock", "all")
    sort = request.args.get("sort", "name")
    order = request.args.get("order", "asc")
    page = parse_int(request.args.get("page"), "page", minimum=1, required=False, default=1)

    query = Product.query
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Product.name.ilike(like), Product.sku.ilike(like), Product.barcode.ilike(like)))
    if category_id:
        query = query.filter(Product.category_id == category_id)
    if status == "active":
        query = query.filter(Product.is_active.is_(True))
    elif status == "inactive":
        query = query.filter(Product.is_active.is_(False))
    if stock == "low":
        query = query.filter(Product.stock_quantity > 0, Product.stock_quantity <= Product.low_stock_threshold)
    elif stock == "out":
        query = query.filter(Product.stock_quantity <= 0)

    column = SORT_COLUMNS.get(sort, Product.name)
    query = query.order_by(column.desc() if order == "desc" else column.asc())

    pagination = query.paginate(page=page, per_page=15, error_out=False)
    categories = Category.query.order_by(Category.name.asc()).all()
    return render_template(
        "products.html",
        pagination=pagination,
        products=pagination.items,
        categories=categories,
        q=q,
        category_id=category_id,
        status=status,
        stock=stock,
        sort=sort,
        order=order,
    )


def _validate_product(form, product=None):
    data = {}
    data["sku"] = clean_str(form.get("sku"), 64)
    if not data["sku"]:
        raise ValidationError("SKU / product code is required.")
    data["barcode"] = clean_str(form.get("barcode"), 64) or None
    data["name"] = clean_str(form.get("name"), 180)
    if not data["name"]:
        raise ValidationError("Product name is required.")
    data["category_id"] = parse_optional_id(form.get("category_id"))
    if data["category_id"] and db.session.get(Category, data["category_id"]) is None:
        raise ValidationError("The selected category does not exist.")
    data["selling_price"] = parse_decimal(form.get("selling_price"), "Selling price", minimum=0)
    data["cost_price"] = parse_decimal(form.get("cost_price") or 0, "Cost price", minimum=0)
    data["discount_percent"] = parse_decimal(
        form.get("discount_percent") or 0, "Discount", minimum=0, maximum=100
    )
    tax_rate = form.get("tax_rate")
    data["tax_rate"] = parse_decimal(tax_rate, "Tax rate", minimum=0, maximum=100, required=False, default=None)
    data["low_stock_threshold"] = parse_int(
        form.get("low_stock_threshold") or get_default_low_stock_threshold(),
        "Low-stock threshold",
        minimum=0,
    )
    data["description"] = clean_str(form.get("description"), 2000) or None
    data["is_active"] = form.get("is_active") == "on" or form.get("is_active") == "1"
    return data


@products_bp.route("/new", methods=["GET", "POST"])
@admin_required
def create():
    if request.method == "POST":
        try:
            data = _validate_product(request.form)
            initial_stock = parse_int(
                request.form.get("stock_quantity") or 0, "Opening stock", minimum=0
            )
            product = Product(**data, stock_quantity=0)
            db.session.add(product)
            db.session.flush()

            if initial_stock > 0:
                product.stock_quantity = initial_stock
                db.session.add(
                    StockMovement(
                        product_id=product.id,
                        user_id=current_user.id,
                        movement_type="purchase",
                        quantity_change=initial_stock,
                        balance_after=initial_stock,
                        reason="Opening stock",
                    )
                )
            audit_service.log_action("product.create", "Product", product.id, details=data["name"])
            db.session.commit()
            flash(f"Product '{product.name}' created.", "success")
            return redirect(url_for("products.index"))
        except ValidationError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        except IntegrityError:
            db.session.rollback()
            flash("A product with this SKU or barcode already exists.", "danger")

    return render_template(
        "product_form.html",
        product=None,
        categories=Category.query.order_by(Category.name.asc()).all(),
    )


@products_bp.route("/<int:product_id>/edit", methods=["GET", "POST"])
@admin_required
def edit(product_id):
    product = db.session.get(Product, product_id)
    if product is None:
        abort(404)

    if request.method == "POST":
        try:
            data = _validate_product(request.form, product=product)
            for key, value in data.items():
                setattr(product, key, value)
            audit_service.log_action("product.update", "Product", product.id, details=data["name"])
            db.session.commit()
            flash(f"Product '{product.name}' updated.", "success")
            return redirect(url_for("products.index"))
        except ValidationError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        except IntegrityError:
            db.session.rollback()
            flash("A product with this SKU or barcode already exists.", "danger")

    return render_template(
        "product_form.html",
        product=product,
        categories=Category.query.order_by(Category.name.asc()).all(),
    )


@products_bp.route("/<int:product_id>/toggle", methods=["POST"])
@admin_required
def toggle(product_id):
    product = db.session.get(Product, product_id)
    if product is None:
        abort(404)
    product.is_active = not product.is_active
    audit_service.log_action(
        "product.activate" if product.is_active else "product.deactivate",
        "Product",
        product.id,
        details=product.name,
    )
    db.session.commit()
    flash(
        f"Product '{product.name}' {'activated' if product.is_active else 'deactivated'}.",
        "success",
    )
    return redirect(request.referrer or url_for("products.index"))


@products_bp.route("/<int:product_id>/delete", methods=["POST"])
@admin_required
def delete(product_id):
    product = db.session.get(Product, product_id)
    if product is None:
        abort(404)

    if product.sale_items.count() > 0:
        # Never delete a product that appears in historical sales: deactivate.
        product.is_active = False
        audit_service.log_action(
            "product.deactivate", "Product", product.id, details=f"{product.name} (has sales history)"
        )
        db.session.commit()
        flash(
            f"'{product.name}' appears in past sales, so it was deactivated instead of deleted.",
            "warning",
        )
        return redirect(url_for("products.index"))

    name = product.name
    db.session.delete(product)
    audit_service.log_action("product.delete", "Product", product_id, details=name)
    db.session.commit()
    flash(f"Product '{name}' deleted.", "success")
    return redirect(url_for("products.index"))


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------
@products_bp.route("/categories", methods=["GET", "POST"])
@admin_required
def categories():
    if request.method == "POST":
        try:
            name = clean_str(request.form.get("name"), 120)
            if not name:
                raise ValidationError("Category name is required.")
            category = Category(name=name, description=clean_str(request.form.get("description"), 255) or None)
            db.session.add(category)
            audit_service.log_action("category.create", "Category", None, details=name)
            db.session.commit()
            flash(f"Category '{name}' added.", "success")
        except ValidationError as exc:
            flash(str(exc), "danger")
        except IntegrityError:
            db.session.rollback()
            flash("That category already exists.", "danger")
        return redirect(url_for("products.categories"))

    return render_template(
        "categories.html",
        categories=Category.query.order_by(Category.name.asc()).all(),
    )
