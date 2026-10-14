"""Read-only reporting and analytics queries.

All figures are derived from persisted sales so nothing is hard-coded.
Datetimes are stored in UTC; "today" is therefore based on UTC.
"""
from datetime import datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func

from extensions import db
from models import Sale, SaleItem
from utils import utcnow


def day_bounds(d):
    if isinstance(d, datetime):
        d = d.date()
    return datetime.combine(d, time.min), datetime.combine(d, time.max)


def _completed(query):
    return query.filter(Sale.status == "completed")


def summarise(start, end):
    """Aggregate totals for completed sales in the [start, end] window."""
    row = _completed(db.session.query(
        func.count(Sale.id),
        func.coalesce(func.sum(Sale.grand_total), 0),
        func.coalesce(func.sum(Sale.subtotal), 0),
        func.coalesce(func.sum(Sale.item_discount), 0),
        func.coalesce(func.sum(Sale.bill_discount), 0),
        func.coalesce(func.sum(Sale.tax_total), 0),
    ).filter(Sale.created_at.between(start, end))).one()
    bills = int(row[0] or 0)
    grand = Decimal(row[1] or 0)
    return {
        "bills": bills,
        "revenue": grand,
        "subtotal": Decimal(row[2] or 0),
        "item_discount": Decimal(row[3] or 0),
        "bill_discount": Decimal(row[4] or 0),
        "discount_total": Decimal(row[3] or 0) + Decimal(row[4] or 0),
        "tax_total": Decimal(row[5] or 0),
        "average_sale": (grand / bills) if bills else Decimal("0.00"),
    }


def today_summary():
    start, end = day_bounds(utcnow())
    return summarise(start, end)


def recent_sales(limit=8):
    return _completed(Sale.query).order_by(Sale.created_at.desc()).limit(limit).all()


def best_sellers(start, end, limit=5):
    return _completed(
        db.session.query(
            SaleItem.product_id,
            SaleItem.product_name,
            SaleItem.sku,
            func.sum(SaleItem.quantity).label("quantity"),
            func.sum(SaleItem.line_total).label("revenue"),
        )
        .join(Sale, SaleItem.sale_id == Sale.id)
        .filter(Sale.created_at.between(start, end))
        .group_by(SaleItem.product_id, SaleItem.product_name, SaleItem.sku)
        .order_by(func.sum(SaleItem.quantity).desc())
    ).limit(limit).all()


def product_sales(start, end, limit=None):
    query = _completed(
        db.session.query(
            SaleItem.product_id,
            SaleItem.product_name,
            SaleItem.sku,
            func.sum(SaleItem.quantity).label("quantity"),
            func.sum(SaleItem.line_total).label("revenue"),
        )
        .join(Sale, SaleItem.sale_id == Sale.id)
        .filter(Sale.created_at.between(start, end))
        .group_by(SaleItem.product_id, SaleItem.product_name, SaleItem.sku)
        .order_by(func.sum(SaleItem.quantity).desc())
    )
    if limit:
        query = query.limit(limit)
    return query.all()


def payment_summary(start, end):
    return _completed(
        db.session.query(
            Sale.payment_method,
            func.count(Sale.id).label("bills"),
            func.coalesce(func.sum(Sale.grand_total), 0).label("amount"),
        )
        .filter(Sale.created_at.between(start, end))
        .group_by(Sale.payment_method)
        .order_by(func.sum(Sale.grand_total).desc())
    ).all()


def sales_in_range(start, end):
    return (
        _completed(Sale.query)
        .filter(Sale.created_at.between(start, end))
        .order_by(Sale.created_at.desc())
        .all()
    )


def _bucket_series(start_dt, buckets, key_func, label_func):
    rows = _completed(
        db.session.query(Sale.created_at, Sale.grand_total)
    ).filter(Sale.created_at >= start_dt).all()
    totals = {}
    counts = {}
    for created_at, grand_total in rows:
        key = key_func(created_at)
        totals[key] = totals.get(key, Decimal("0")) + Decimal(grand_total or 0)
        counts[key] = counts.get(key, 0) + 1
    labels = [label_func(b) for b in buckets]
    revenue = [float(totals.get(b, Decimal("0"))) for b in buckets]
    bills = [counts.get(b, 0) for b in buckets]
    return {"labels": labels, "revenue": revenue, "bills": bills}


def revenue_by_day(days=14):
    today = utcnow().date()
    start_day = today - timedelta(days=days - 1)
    start_dt = datetime.combine(start_day, time.min)
    buckets = [start_day + timedelta(days=i) for i in range(days)]
    return _bucket_series(start_dt, buckets, lambda dt: dt.date(), lambda b: b.strftime("%d %b"))


def revenue_by_week(weeks=8):
    today = utcnow().date()
    monday = today - timedelta(days=today.weekday())
    buckets = [monday - timedelta(weeks=(weeks - 1 - i)) for i in range(weeks)]
    start_dt = datetime.combine(buckets[0], time.min)

    def key_func(dt):
        d = dt.date()
        return d - timedelta(days=d.weekday())

    def label_func(b):
        return b.strftime("%d %b")

    return _bucket_series(start_dt, buckets, key_func, label_func)


def revenue_by_month(months=6):
    today = utcnow().date().replace(day=1)
    buckets = []
    year, month = today.year, today.month
    for _ in range(months):
        buckets.append((year, month))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    buckets.reverse()
    start_dt = datetime(buckets[0][0], buckets[0][1], 1, 0, 0, 0)

    def key_func(dt):
        return (dt.year, dt.month)

    def label_func(b):
        return datetime(b[0], b[1], 1).strftime("%b %Y")

    return _bucket_series(start_dt, buckets, key_func, label_func)


def dashboard_stats():
    from services import inventory_service
    from models import Product

    today = today_summary()
    stock = inventory_service.counts()
    active_products = Product.query.filter(Product.is_active.is_(True)).count()
    start_30 = datetime.combine(utcnow().date() - timedelta(days=29), time.min)
    end = utcnow()
    return {
        "today_sales": today,
        "active_products": active_products,
        "low_stock": stock["low"],
        "out_of_stock": stock["out"],
        "recent_sales": recent_sales(6),
        "best_sellers": best_sellers(start_30, end, 5),
        "daily": revenue_by_day(14),
        "weekly": revenue_by_week(8),
        "monthly": revenue_by_month(6),
    }
