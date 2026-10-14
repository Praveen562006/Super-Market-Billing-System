"""Point-of-sale, checkout and invoice retrieval."""
from flask import (
    Blueprint,
    abort,
    jsonify,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import or_

from extensions import db
from models import Category, Product, Sale
from services import billing_service
from services.billing_service import BillingError

billing_bp = Blueprint("billing", __name__)


def _visible_sales_query():
    query = Sale.query
    # Cashiers see the transactions they created; admins see everything.
    if not current_user.is_admin:
        query = query.filter(Sale.cashier_id == current_user.id)
    return query


@billing_bp.route("/")
@login_required
def index():
    categories = Category.query.filter(Category.is_active.is_(True)).order_by(Category.name.asc()).all()
    return render_template("billing.html", categories=categories)


@billing_bp.route("/products")
@login_required
def search_products():
    q = (request.args.get("q") or "").strip()
    category_id = request.args.get("category") or ""
    query = Product.query.filter(Product.is_active.is_(True))
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(Product.name.ilike(like), Product.sku.ilike(like), Product.barcode.ilike(like))
        )
    if category_id.isdigit():
        query = query.filter(Product.category_id == int(category_id))
    products = query.order_by(Product.name.asc()).limit(20).all()
    return jsonify(
        {
            "success": True,
            "products": [
                {
                    "id": p.id,
                    "sku": p.sku,
                    "barcode": p.barcode,
                    "name": p.name,
                    "category": p.category.name if p.category else None,
                    "selling_price": float(p.selling_price or 0),
                    "discount_percent": float(p.discount_percent or 0),
                    "tax_rate": float(p.effective_tax_rate or 0),
                    "stock_quantity": p.stock_quantity,
                }
                for p in products
            ],
        }
    )


@billing_bp.route("/checkout", methods=["POST"])
@login_required
def checkout():
    payload = request.get_json(silent=True) or request.form
    items = payload.get("items")
    if isinstance(items, str):
        import json

        try:
            items = json.loads(items)
        except ValueError:
            items = []
    try:
        sale = billing_service.create_sale(
            cashier=current_user,
            items=items or [],
            payment_method=payload.get("payment_method", "cash"),
            amount_received=payload.get("amount_received"),
            customer_mobile=(payload.get("customer_mobile") or "").strip() or None,
            customer_name=(payload.get("customer_name") or "").strip() or None,
            bill_discount_percent=payload.get("bill_discount_percent") or 0,
            client_token=(payload.get("client_token") or "").strip() or None,
            notes=(payload.get("notes") or "").strip() or None,
        )
    except BillingError as exc:
        db.session.rollback()
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:  # pragma: no cover - unexpected
        db.session.rollback()
        return jsonify({"success": False, "message": "Could not complete the sale."}), 500

    return jsonify(
        {
            "success": True,
            "sale_id": sale.id,
            "invoice_number": sale.invoice_number,
            "grand_total": float(sale.grand_total),
            "change_due": float(sale.change_due),
            "invoice_url": url_for("billing.invoice", sale_id=sale.id),
            "print_url": url_for("billing.invoice_print", sale_id=sale.id),
        }
    )


@billing_bp.route("/sales")
@login_required
def sales():
    page = request.args.get("page", 1, type=int)
    q = (request.args.get("q") or "").strip()
    query = _visible_sales_query()
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Sale.invoice_number.ilike(like), Sale.customer_mobile.ilike(like)))
    pagination = query.order_by(Sale.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template("sales.html", pagination=pagination, sales=pagination.items, q=q)


def _get_sale_or_404(sale_id):
    sale = db.session.get(Sale, sale_id)
    if sale is None:
        abort(404)
    if not current_user.is_admin and sale.cashier_id != current_user.id:
        abort(403)
    return sale


@billing_bp.route("/sales/<int:sale_id>")
@login_required
def invoice(sale_id):
    sale = _get_sale_or_404(sale_id)
    return render_template("invoice.html", sale=sale, printable=False)


@billing_bp.route("/sales/<int:sale_id>/print")
@login_required
def invoice_print(sale_id):
    sale = _get_sale_or_404(sale_id)
    return render_template("invoice.html", sale=sale, printable=True)


@billing_bp.route("/sales/<int:sale_id>/pdf")
@login_required
def invoice_pdf(sale_id):
    sale = _get_sale_or_404(sale_id)
    try:
        from services.invoice_service import render_invoice_pdf

        pdf_bytes = render_invoice_pdf(sale)
    except ImportError:
        abort(503, "PDF generation is unavailable.")
    from io import BytesIO

    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{sale.invoice_number}.pdf",
    )
