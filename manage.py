"""Command-line utilities: database init, admin provisioning and migration.

Examples::

    python manage.py init
    python manage.py create-admin --username admin
    python manage.py seed-demo
    python manage.py migrate-mongo --mongo-url mongodb://127.0.0.1:27017/supermarket
    python manage.py reset-db --yes
"""
import argparse
import secrets
import sys
from decimal import Decimal, InvalidOperation

from sqlalchemy import func

import models  # noqa: F401  (ensures all tables are registered)
from app import create_app
from extensions import db
from models import Category, Product, Sale, SaleItem, Setting, User
from services.settings_service import ensure_defaults, get_default_low_stock_threshold
from utils import utcnow


def ensure_admin(app, username=None, password=None, name=None):
    username = username or app.config.get("ADMIN_USERNAME", "admin")
    name = name or app.config.get("ADMIN_NAME", "Store Administrator")
    password = password or app.config.get("ADMIN_PASSWORD") or ""

    existing = User.query.filter(func.lower(User.username) == username.lower()).first()
    if existing:
        print(f"[skip] Administrator '{username}' already exists.")
        return

    generated = False
    if not password:
        password = secrets.token_urlsafe(12)
        generated = True
    user = User(username=username, full_name=name, role=User.ROLE_ADMIN, is_active=True)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    print(f"[ok] Created administrator '{username}'.")
    if generated:
        print("=" * 64)
        print(f"  Generated password for '{username}': {password}")
        print("  Store it safely and change it after the first login.")
        print("=" * 64)


def cmd_init(args):
    app = create_app()
    with app.app_context():
        db.create_all()
        ensure_defaults()
        if Category.query.count() == 0:
            db.session.add(Category(name="General", description="Default category"))
            db.session.commit()
        ensure_admin(app, args.username, args.password, args.name)
        print("[ok] Database initialised.")


def cmd_create_admin(args):
    app = create_app()
    with app.app_context():
        db.create_all()
        ensure_defaults()
        ensure_admin(app, args.username, args.password, args.name)


def cmd_seed_demo(args):
    app = create_app()
    with app.app_context():
        db.create_all()
        ensure_defaults()
        category = Category.query.filter(func.lower(Category.name) == "beverages").first()
        if not category:
            category = Category(name="Beverages", description="Sample category")
            db.session.add(category)
            db.session.flush()

        samples = [
            ("SKU-1001", "Spring Water 1L", "25.00", "18.00", 0, 120),
            ("SKU-1002", "Orange Juice 1L", "90.00", "62.00", 5, 60),
            ("SKU-1003", "Cola 500ml", "40.00", "28.00", 0, 8),
            ("SKU-1004", "Green Tea 250ml", "55.00", "38.00", 10, 0),
            ("SKU-1005", "Milk 1L", "48.00", "36.00", 0, 45),
        ]
        created = 0
        for sku, name, price, cost, discount, stock in samples:
            if Product.query.filter_by(sku=sku).first():
                continue
            db.session.add(
                Product(
                    sku=sku,
                    name=name,
                    category_id=category.id,
                    selling_price=Decimal(price),
                    cost_price=Decimal(cost),
                    discount_percent=Decimal(discount),
                    stock_quantity=stock,
                    low_stock_threshold=get_default_low_stock_threshold(),
                    is_active=True,
                )
            )
            created += 1
        db.session.commit()
        print(f"[ok] Seeded {created} demo product(s).")


def cmd_reset_db(args):
    app = create_app()
    if not args.yes:
        print("Refusing to reset without --yes.")
        return 1
    with app.app_context():
        confirm = input(
            "This will DELETE all data in the current database. Type 'reset' to confirm: "
        )
        if confirm.strip().lower() != "reset":
            print("Aborted.")
            return 1
        db.drop_all()
        db.create_all()
        ensure_defaults()
        db.session.add(Category(name="General", description="Default category"))
        db.session.commit()
        ensure_admin(app, args.username, args.password, args.name)
        print("[ok] Database reset.")


def cmd_migrate_mongo(args):
    try:
        from pymongo import MongoClient
    except ImportError:
        print("pymongo is not installed. Run: pip install pymongo")
        return 1

    app = create_app()
    client = MongoClient(args.mongo_url, serverSelectionTimeoutMS=4000)
    try:
        client.server_info()
    except Exception as exc:  # pragma: no cover - requires a live Mongo
        print(f"[error] Could not connect to MongoDB: {exc}")
        return 1

    mongo_db = client[args.dbname]
    with app.app_context():
        db.create_all()
        ensure_defaults()

        product_map = {}
        migrated_products = 0
        for doc in mongo_db.products.find():
            legacy_id = doc.get("p_id")
            sku = f"P{int(legacy_id):05d}" if legacy_id is not None else f"LEG{str(doc['_id'])[-6:]}"
            existing = Product.query.filter_by(sku=sku).first()
            if existing:
                product_map[legacy_id] = existing.id
                continue
            product = Product(
                sku=sku,
                name=doc.get("name", "Unnamed"),
                selling_price=_dec(doc.get("price")),
                discount_percent=_dec(doc.get("discount")),
                stock_quantity=0,
                low_stock_threshold=get_default_low_stock_threshold(),
                is_active=True,
            )
            db.session.add(product)
            db.session.flush()
            product_map[legacy_id] = product.id
            migrated_products += 1
        db.session.commit()
        print(f"[ok] Migrated {migrated_products} product(s).")

        migrated_users = 0
        for doc in mongo_db.users.find():
            username = doc.get("username")
            if not username or User.query.filter(func.lower(User.username) == username.lower()).first():
                continue
            user = User(username=username, role=User.ROLE_CASHIER, is_active=False)
            user.set_password(secrets.token_urlsafe(16))
            db.session.add(user)
            migrated_users += 1
        db.session.commit()
        print(f"[ok] Migrated {migrated_users} user(s) (disabled; reset their password).")

        migrated_bills = 0
        for doc in mongo_db.bills.find():
            existing = Sale.query.filter_by(client_token=f"mongo-{doc['_id']}").first()
            if existing:
                continue
            sale = _sale_from_legacy(doc, product_map)
            db.session.add(sale)
            db.session.flush()
            from services.invoice_service import build_invoice_number

            when = doc.get("createdAt") or utcnow()
            sale.invoice_number = build_invoice_number(sale.id, when)
            db.session.flush()
            migrated_bills += 1
        db.session.commit()
        print(f"[ok] Migrated {migrated_bills} bill(s).")
    print("[done] MongoDB migration complete.")


def _dec(value):
    try:
        return Decimal(str(value if value is not None else 0))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _sale_from_legacy(doc, product_map):
    when = doc.get("createdAt") or utcnow()
    items = doc.get("bill") or []
    subtotal = Decimal("0")
    item_discount = Decimal("0")
    sale = Sale(
        invoice_number="PENDING",
        client_token=f"mongo-{doc['_id']}",
        customer_mobile=str(doc.get("mobile")) if doc.get("mobile") is not None else None,
        payment_method=(doc.get("method") or "cash"),
        status="completed",
        created_at=when,
    )
    for line in items:
        try:
            qty = int(line.get("quantity") or 1)
        except (TypeError, ValueError):
            qty = 1
        price = _dec(line.get("price"))
        discount = _dec(line.get("discount"))
        gross = price * qty
        disc = gross * discount / Decimal("100")
        subtotal += gross
        item_discount += disc
        legacy_id = line.get("p_id")
        sale.items.append(
            SaleItem(
                product_id=product_map.get(legacy_id),
                product_name=line.get("name") or "Item",
                sku=f"P{int(legacy_id):05d}" if legacy_id is not None else "LEGACY",
                unit_price=price,
                quantity=qty,
                discount_percent=discount,
                discount_amount=disc,
                tax_rate=Decimal("0"),
                tax_amount=Decimal("0"),
                line_total=gross - disc,
            )
        )
    sale.subtotal = subtotal
    sale.item_discount = item_discount
    sale.tax_total = Decimal("0")
    try:
        sale.grand_total = _dec(doc.get("amt"))
    except Exception:
        sale.grand_total = subtotal - item_discount
    sale.amount_received = sale.grand_total
    sale.change_due = Decimal("0")
    return sale


def main():
    parser = argparse.ArgumentParser(description="SuperMarket Billing System management")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Create tables and the initial administrator")
    p_init.add_argument("--username")
    p_init.add_argument("--password")
    p_init.add_argument("--name")
    p_init.set_defaults(func=cmd_init)

    p_admin = sub.add_parser("create-admin", help="Create an administrator account")
    p_admin.add_argument("--username")
    p_admin.add_argument("--password")
    p_admin.add_argument("--name")
    p_admin.set_defaults(func=cmd_create_admin)

    p_seed = sub.add_parser("seed-demo", help="Insert sample products for testing")
    p_seed.set_defaults(func=cmd_seed_demo)

    p_migrate = sub.add_parser("migrate-mongo", help="Import data from the legacy MongoDB")
    p_migrate.add_argument("--mongo-url", default="mongodb://127.0.0.1:27017/supermarket")
    p_migrate.add_argument("--dbname", default="supermarket")
    p_migrate.set_defaults(func=cmd_migrate_mongo)

    p_reset = sub.add_parser("reset-db", help="Drop and recreate the database (destructive)")
    p_reset.add_argument("--yes", action="store_true")
    p_reset.add_argument("--username")
    p_reset.add_argument("--password")
    p_reset.add_argument("--name")
    p_reset.set_defaults(func=cmd_reset_db)

    args = parser.parse_args()
    sys.exit(args.func(args) or 0)


if __name__ == "__main__":
    main()
