"""Shared pytest fixtures.

The app is created with the ``testing`` config (in-memory SQLite, CSRF off)
and a small, deterministic data set is seeded for every test.
"""
from decimal import Decimal

import pytest

from app import create_app
from extensions import db
from models import Category, Product, User
from services.settings_service import ensure_defaults

ADMIN_PASSWORD = "adminpass123"
CASHIER_PASSWORD = "cashierpass123"


@pytest.fixture
def app():
    application = create_app("testing")
    with application.app_context():
        db.create_all()
        ensure_defaults()

        admin = User(username="admin", full_name="Admin User", role=User.ROLE_ADMIN, is_active=True)
        admin.set_password(ADMIN_PASSWORD)
        cashier = User(username="cashier", full_name="Cashier User", role=User.ROLE_CASHIER, is_active=True)
        cashier.set_password(CASHIER_PASSWORD)
        disabled = User(username="disabled", role=User.ROLE_CASHIER, is_active=False)
        disabled.set_password(CASHIER_PASSWORD)

        category = Category(name="General", description="Default category")
        db.session.add_all([admin, cashier, disabled, category])
        db.session.flush()

        water = Product(
            sku="SKU-1001",
            name="Spring Water",
            category_id=category.id,
            selling_price=Decimal("25.00"),
            cost_price=Decimal("18.00"),
            discount_percent=Decimal("0.00"),
            stock_quantity=100,
            low_stock_threshold=10,
        )
        juice = Product(
            sku="SKU-1002",
            name="Orange Juice",
            category_id=category.id,
            selling_price=Decimal("90.00"),
            cost_price=Decimal("62.00"),
            discount_percent=Decimal("10.00"),
            stock_quantity=5,
            low_stock_threshold=10,
        )
        db.session.add_all([water, juice])
        db.session.commit()

        application.config["SEED"] = {
            "admin_id": admin.id,
            "cashier_id": cashier.id,
            "water_id": water.id,
            "juice_id": juice.id,
            "category_id": category.id,
        }
        yield application

        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def login(client):
    def _login(username="admin", password=ADMIN_PASSWORD):
        return client.post(
            "/login",
            data={"username": username, "password": password},
            follow_redirects=True,
        )

    return _login
