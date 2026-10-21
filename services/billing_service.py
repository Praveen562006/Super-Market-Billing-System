"""Authoritative billing / checkout logic.

All monetary calculations happen here on the server.  The browser only sends
product ids and quantities; prices, discounts, taxes and totals are always
read from the database so a tampered client cannot influence the totals.
"""
from decimal import ROUND_HALF_UP, Decimal

from extensions import db
from models import Payment, Product, Sale, SaleItem, StockMovement
from services import audit_service, customer_service, inventory_service, settings_service
from services.invoice_service import build_invoice_number

TWO_PLACES = Decimal("0.01")
HUNDRED = Decimal("100")
ALLOWED_PAYMENT_METHODS = ("cash", "card", "online")


class BillingError(Exception):
    """Base class for user-correctable billing problems."""


class EmptyCartError(BillingError):
    pass


class InvalidPaymentError(BillingError):
    pass


class InsufficientStockError(BillingError):
    pass


def money(value):
    return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def normalize_percent(value, field="percentage"):
    try:
        value = Decimal(str(value if value is not None else 0))
    except Exception:
        raise BillingError(f"Invalid {field}.")
    if value < 0 or value > 100:
        raise BillingError(f"{field.capitalize()} must be between 0 and 100.")
    return value


def _parse_cart(items):
    """Aggregate a cart into {product_id: quantity}, validating input."""
    quantities = {}
    for raw in items or []:
        try:
            pid = int(raw.get("product_id"))
            qty = int(raw.get("quantity"))
        except (AttributeError, TypeError, ValueError):
            raise BillingError("The cart contains an invalid item.")
        if qty <= 0:
            raise BillingError("Every quantity must be a positive whole number.")
        quantities[pid] = quantities.get(pid, 0) + qty
    if not quantities:
        raise EmptyCartError("Cannot check out an empty cart.")
    return quantities


def create_sale(
    *,
    cashier,
    items,
    payment_method="cash",
    amount_received=None,
    customer_mobile=None,
    customer_name=None,
    bill_discount_percent=0,
    client_token=None,
    notes=None,
):
    """Validate, price and persist a sale, deducting stock atomically.

    Returns the persisted :class:`Sale`.  Raises :class:`BillingError`
    subclasses on any validation problem.  Safe to retry with the same
    ``client_token`` (duplicate submissions return the original sale).
    """
    # Idempotency: a repeated submit with the same token returns the first sale.
    if client_token:
        existing = Sale.query.filter_by(client_token=client_token).first()
        if existing is not None:
            return existing

    payment_method = (payment_method or "cash").strip().lower()
    if payment_method not in ALLOWED_PAYMENT_METHODS:
        raise InvalidPaymentError("Unsupported payment method.")

    quantities = _parse_cart(items)

    products = {
        p.id: p for p in Product.query.filter(Product.id.in_(list(quantities))).all()
    }

    for pid, qty in quantities.items():
        product = products.get(pid)
        if product is None or not product.is_active:
            raise BillingError("A product in the cart is no longer available.")
        if product.stock_quantity < qty:
            raise InsufficientStockError(
                f"Not enough stock for '{product.name}' "
                f"(available: {product.stock_quantity})."
            )

    bill_discount_percent = normalize_percent(bill_discount_percent, "bill discount")
    if bill_discount_percent > settings_service.get_max_bill_discount():
        raise BillingError("Bill discount exceeds the configured maximum.")

    subtotal = Decimal("0.00")
    item_discount_total = Decimal("0.00")
    tax_total = Decimal("0.00")
    lines = []

    for pid, qty in quantities.items():
        product = products[pid]
        unit_price = money(product.selling_price)
        gross = money(unit_price * qty)
        discount_percent = normalize_percent(product.discount_percent, "product discount")
        discount_amount = money(gross * discount_percent / HUNDRED)
        taxable = gross - discount_amount
        tax_rate = normalize_percent(product.effective_tax_rate, "tax rate")
        tax_amount = money(taxable * tax_rate / HUNDRED)
        line_total = money(taxable + tax_amount)

        subtotal += gross
        item_discount_total += discount_amount
        tax_total += tax_amount
        lines.append(
            {
                "product_id": pid,
                "product_name": product.name,
                "sku": product.sku,
                "unit_price": unit_price,
                "quantity": qty,
                "discount_percent": discount_percent,
                "discount_amount": discount_amount,
                "tax_rate": tax_rate,
                "tax_amount": tax_amount,
                "line_total": line_total,
            }
        )

    subtotal = money(subtotal)
    item_discount_total = money(item_discount_total)
    tax_total = money(tax_total)
    after_item_discount = money(subtotal - item_discount_total)
    bill_discount_amount = money(after_item_discount * bill_discount_percent / HUNDRED)
    grand_total = money(after_item_discount + tax_total - bill_discount_amount)
    if grand_total < 0:
        grand_total = Decimal("0.00")

    if payment_method == "cash":
        try:
            received = money(amount_received if amount_received not in (None, "") else 0)
        except Exception:
            raise BillingError("Invalid amount received.")
        if received < grand_total:
            raise BillingError("Amount received is less than the grand total.")
    else:
        received = grand_total
    change_due = money(received - grand_total)

    # -- Commit stock changes atomically; roll back everything on failure ---
    try:
        for pid, qty in quantities.items():
            if not inventory_service.decrement_stock_atomic(pid, qty):
                raise InsufficientStockError(
                    f"Not enough stock for '{products[pid].name}'."
                )

        sale = Sale(
            invoice_number="PENDING",
            client_token=client_token or None,
            cashier_id=cashier.id,
            customer_mobile=(customer_mobile or None),
            customer_name=(customer_name or None),
            subtotal=subtotal,
            item_discount=item_discount_total,
            bill_discount_percent=bill_discount_percent,
            bill_discount=bill_discount_amount,
            tax_total=tax_total,
            grand_total=grand_total,
            payment_method=payment_method,
            amount_received=received,
            change_due=change_due,
            status="completed",
            notes=notes,
        )
        db.session.add(sale)
        db.session.flush()  # assigns sale.id and created_at
        sale.invoice_number = build_invoice_number(sale.id, sale.created_at)
        db.session.flush()

        for line in lines:
            db.session.add(
                SaleItem(
                    sale_id=sale.id,
                    product_id=line["product_id"],
                    product_name=line["product_name"],
                    sku=line["sku"],
                    unit_price=line["unit_price"],
                    quantity=line["quantity"],
                    discount_percent=line["discount_percent"],
                    discount_amount=line["discount_amount"],
                    tax_rate=line["tax_rate"],
                    tax_amount=line["tax_amount"],
                    line_total=line["line_total"],
                )
            )
            product = db.session.get(Product, line["product_id"])
            db.session.refresh(product)
            db.session.add(
                StockMovement(
                    product_id=line["product_id"],
                    user_id=cashier.id,
                    sale_id=sale.id,
                    movement_type="sale",
                    quantity_change=-line["quantity"],
                    balance_after=product.stock_quantity,
                    reason=f"Sale {sale.invoice_number}",
                )
            )

        db.session.add(
            Payment(sale_id=sale.id, method=payment_method, amount=grand_total)
        )
        # Remember the buyer so their name auto-fills next time.
        if sale.customer_mobile:
            customer_service.register(sale.customer_mobile, sale.customer_name)
        audit_service.log_action(
            "sale.create",
            entity="Sale",
            entity_id=sale.id,
            details=f"{sale.invoice_number} total={grand_total} method={payment_method}",
        )
        db.session.commit()
        return sale
    except Exception:
        db.session.rollback()
        raise


def preview_sale(items, bill_discount_percent=0):
    """Read-only price preview (used for server-side verification)."""
    quantities = _parse_cart(items)
    products = {
        p.id: p for p in Product.query.filter(Product.id.in_(list(quantities))).all()
    }
    bill_discount_percent = normalize_percent(bill_discount_percent, "bill discount")
    subtotal = Decimal("0.00")
    discount_total = Decimal("0.00")
    tax_total = Decimal("0.00")
    lines = []
    for pid, qty in quantities.items():
        product = products.get(pid)
        if product is None:
            raise BillingError("Product not found.")
        unit_price = money(product.selling_price)
        gross = money(unit_price * qty)
        discount_percent = normalize_percent(product.discount_percent)
        discount_amount = money(gross * discount_percent / HUNDRED)
        taxable = gross - discount_amount
        tax_rate = normalize_percent(product.effective_tax_rate)
        tax_amount = money(taxable * tax_rate / HUNDRED)
        line_total = money(taxable + tax_amount)
        subtotal += gross
        discount_total += discount_amount
        tax_total += tax_amount
        lines.append(
            {
                "product_id": pid,
                "product_name": product.name,
                "sku": product.sku,
                "unit_price": float(unit_price),
                "quantity": qty,
                "stock_quantity": product.stock_quantity,
                "discount_percent": float(discount_percent),
                "tax_rate": float(tax_rate),
                "line_total": float(line_total),
            }
        )
    after_item = money(subtotal - discount_total)
    bill_discount = money(after_item * bill_discount_percent / HUNDRED)
    grand_total = money(after_item + tax_total - bill_discount)
    return {
        "lines": lines,
        "subtotal": float(money(subtotal)),
        "item_discount": float(money(discount_total)),
        "tax_total": float(money(tax_total)),
        "bill_discount": float(bill_discount),
        "grand_total": float(grand_total),
    }
