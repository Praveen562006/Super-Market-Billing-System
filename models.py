"""SQLAlchemy models for the SuperMarket Billing System.

The schema keeps the original concepts (products with a price and a
percentage discount, bills with a payment method) while adding the fields
required for a real point-of-sale / inventory application: roles, stock
tracking, stock movements, audit logs and payments.
"""
from decimal import Decimal

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db
from utils import utcnow

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
MONEY = lambda: db.Numeric(12, 2)  # noqa: E731


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Users / roles
# ---------------------------------------------------------------------------
class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(120))
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="cashier", index=True)
    # Column overrides UserMixin's property -> inactive users cannot log in.
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    last_login_at = db.Column(db.DateTime)

    sales = db.relationship("Sale", back_populates="cashier", lazy="dynamic")
    movements = db.relationship("StockMovement", back_populates="user", lazy="dynamic")

    ROLE_ADMIN = "admin"
    ROLE_CASHIER = "cashier"

    @property
    def is_admin(self):
        return self.role == self.ROLE_ADMIN

    @property
    def is_cashier(self):
        return self.role == self.ROLE_CASHIER

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    def display_name(self):
        return self.full_name or self.username

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------
class Category(TimestampMixin, db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False, index=True)
    description = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    products = db.relationship("Product", back_populates="category", lazy="dynamic")

    def __repr__(self):
        return f"<Category {self.name}>"


class Product(TimestampMixin, db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(64), unique=True, nullable=False, index=True)
    barcode = db.Column(db.String(64), unique=True, index=True)
    name = db.Column(db.String(180), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), index=True)

    selling_price = db.Column(MONEY(), nullable=False, default=Decimal("0.00"))
    cost_price = db.Column(MONEY(), nullable=False, default=Decimal("0.00"))
    discount_percent = db.Column(db.Numeric(5, 2), nullable=False, default=Decimal("0.00"))
    tax_rate = db.Column(db.Numeric(5, 2), nullable=True)  # None -> use store default

    stock_quantity = db.Column(db.Integer, nullable=False, default=0)
    low_stock_threshold = db.Column(db.Integer, nullable=False, default=10)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)

    category = db.relationship("Category", back_populates="products")
    sale_items = db.relationship("SaleItem", back_populates="product", lazy="dynamic")
    movements = db.relationship("StockMovement", back_populates="product", lazy="dynamic")

    __table_args__ = (
        db.CheckConstraint("stock_quantity >= 0", name="ck_product_stock_non_negative"),
        db.CheckConstraint("selling_price >= 0", name="ck_product_price_non_negative"),
        db.CheckConstraint("cost_price >= 0", name="ck_product_cost_non_negative"),
        db.CheckConstraint(
            "discount_percent >= 0 AND discount_percent <= 100",
            name="ck_product_discount_range",
        ),
    )

    @property
    def effective_tax_rate(self):
        if self.tax_rate is not None:
            return Decimal(self.tax_rate)
        from services.settings_service import get_default_tax_rate

        return get_default_tax_rate()

    @property
    def is_low_stock(self):
        return 0 < self.stock_quantity <= self.low_stock_threshold

    @property
    def is_out_of_stock(self):
        return self.stock_quantity <= 0

    @property
    def is_referenced(self):
        """True if the product has ever been part of a completed sale."""
        return self.sale_items.count() > 0

    def __repr__(self):
        return f"<Product {self.sku} {self.name}>"


# ---------------------------------------------------------------------------
# Sales / billing
# ---------------------------------------------------------------------------
class Sale(db.Model):
    __tablename__ = "sales"

    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(40), unique=True, nullable=False, index=True)
    client_token = db.Column(db.String(64), unique=True, index=True)  # idempotency key

    cashier_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    customer_mobile = db.Column(db.String(20))
    customer_name = db.Column(db.String(120))

    subtotal = db.Column(MONEY(), nullable=False, default=Decimal("0.00"))
    item_discount = db.Column(MONEY(), nullable=False, default=Decimal("0.00"))
    bill_discount_percent = db.Column(db.Numeric(5, 2), nullable=False, default=Decimal("0.00"))
    bill_discount = db.Column(MONEY(), nullable=False, default=Decimal("0.00"))
    tax_total = db.Column(MONEY(), nullable=False, default=Decimal("0.00"))
    grand_total = db.Column(MONEY(), nullable=False, default=Decimal("0.00"))

    payment_method = db.Column(db.String(30), nullable=False, default="cash")
    amount_received = db.Column(MONEY(), nullable=False, default=Decimal("0.00"))
    change_due = db.Column(MONEY(), nullable=False, default=Decimal("0.00"))

    status = db.Column(db.String(20), nullable=False, default="completed", index=True)
    notes = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)

    cashier = db.relationship("User", back_populates="sales")
    items = db.relationship(
        "SaleItem", back_populates="sale", cascade="all, delete-orphan", lazy="selectin"
    )
    payments = db.relationship(
        "Payment", back_populates="sale", cascade="all, delete-orphan", lazy="selectin"
    )
    movements = db.relationship("StockMovement", back_populates="sale", lazy="dynamic")

    @property
    def total_quantity(self):
        return sum(int(i.quantity) for i in self.items)

    def __repr__(self):
        return f"<Sale {self.invoice_number} {self.grand_total}>"


class SaleItem(db.Model):
    __tablename__ = "sale_items"

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id", ondelete="CASCADE"), nullable=False, index=True)
    # Nullable so historical sale lines survive if a product is removed.
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), index=True)

    # Snapshot of the product information at the moment of sale.
    product_name = db.Column(db.String(180), nullable=False)
    sku = db.Column(db.String(64), nullable=False)

    unit_price = db.Column(MONEY(), nullable=False, default=Decimal("0.00"))
    quantity = db.Column(db.Integer, nullable=False, default=1)
    discount_percent = db.Column(db.Numeric(5, 2), nullable=False, default=Decimal("0.00"))
    discount_amount = db.Column(MONEY(), nullable=False, default=Decimal("0.00"))
    tax_rate = db.Column(db.Numeric(5, 2), nullable=False, default=Decimal("0.00"))
    tax_amount = db.Column(MONEY(), nullable=False, default=Decimal("0.00"))
    line_total = db.Column(MONEY(), nullable=False, default=Decimal("0.00"))

    sale = db.relationship("Sale", back_populates="items")
    product = db.relationship("Product", back_populates="sale_items")

    __table_args__ = (
        db.CheckConstraint("quantity > 0", name="ck_sale_item_qty_positive"),
    )


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id", ondelete="CASCADE"), nullable=False, index=True)
    method = db.Column(db.String(30), nullable=False)
    amount = db.Column(MONEY(), nullable=False, default=Decimal("0.00"))
    reference = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    sale = db.relationship("Sale", back_populates="payments")


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------
class StockMovement(db.Model):
    __tablename__ = "stock_movements"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id"), index=True)

    movement_type = db.Column(db.String(30), nullable=False)  # sale, purchase, adjustment, return
    quantity_change = db.Column(db.Integer, nullable=False)   # negative for out
    balance_after = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)

    product = db.relationship("Product", back_populates="movements")
    user = db.relationship("User", back_populates="movements")
    sale = db.relationship("Sale", back_populates="movements")


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------
class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    action = db.Column(db.String(80), nullable=False, index=True)
    entity = db.Column(db.String(80))
    entity_id = db.Column(db.String(40))
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)

    user = db.relationship("User")


# ---------------------------------------------------------------------------
# Settings (key/value) + invoice sequence
# ---------------------------------------------------------------------------
class Setting(db.Model):
    __tablename__ = "settings"

    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.String(255))
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)
