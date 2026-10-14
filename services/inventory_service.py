"""Inventory operations: atomic stock changes and stock-level queries."""
from flask import current_app
from sqlalchemy import func, update

from extensions import db
from models import Product, StockMovement


class InventoryError(Exception):
    """Raised when a stock operation would produce an invalid state."""


def _movement(product, quantity_change, movement_type, reason, user_id, sale_id, balance_after):
    return StockMovement(
        product_id=product.id,
        user_id=user_id,
        sale_id=sale_id,
        movement_type=movement_type,
        quantity_change=quantity_change,
        balance_after=balance_after,
        reason=reason,
    )


def decrement_stock_atomic(product_id, quantity):
    """Atomically subtract *quantity* from a product's stock.

    Uses a single conditional UPDATE so two concurrent checkouts can never
    drive stock below zero: the row is only updated when enough stock is
    available.  Returns True on success, False when stock is insufficient.
    """
    if quantity <= 0:
        raise InventoryError("Quantity must be positive.")
    result = db.session.execute(
        update(Product)
        .where(Product.id == product_id, Product.stock_quantity >= quantity)
        .values(stock_quantity=Product.stock_quantity - quantity)
    )
    return result.rowcount == 1


def adjust_stock(product, quantity_change, movement_type="adjustment", reason=None, user_id=None):
    """Apply a manual stock change (positive or negative) and log a movement."""
    quantity_change = int(quantity_change)
    new_balance = int(product.stock_quantity) + quantity_change
    if new_balance < 0:
        raise InventoryError(
            f"Adjustment would make stock negative for '{product.name}'."
        )
    product.stock_quantity = new_balance
    db.session.add(
        _movement(product, quantity_change, movement_type, reason, user_id, None, new_balance)
    )
    return new_balance


def stock_overview(query=None):
    """Return products ordered so that the most urgent restocks come first."""
    q = query if query is not None else Product.query
    return q.order_by(
        (Product.stock_quantity <= 0).desc(),
        (Product.stock_quantity <= Product.low_stock_threshold).desc(),
        Product.stock_quantity.asc(),
    )


def low_stock_query():
    return Product.query.filter(
        Product.is_active.is_(True),
        Product.stock_quantity > 0,
        Product.stock_quantity <= Product.low_stock_threshold,
    )


def out_of_stock_query():
    return Product.query.filter(
        Product.is_active.is_(True), Product.stock_quantity <= 0
    )


def counts():
    total = Product.query.filter(Product.is_active.is_(True)).count()
    low = low_stock_query().count()
    out = out_of_stock_query().count()
    return {"total": total, "low": low, "out": out}


def total_stock_value():
    """Current retail value of all stock (cost and retail)."""
    row = db.session.query(
        func.coalesce(func.sum(Product.stock_quantity * Product.selling_price), 0),
        func.coalesce(func.sum(Product.stock_quantity * Product.cost_price), 0),
    ).filter(Product.is_active.is_(True)).one()
    return {"retail": row[0] or 0, "cost": row[1] or 0}
