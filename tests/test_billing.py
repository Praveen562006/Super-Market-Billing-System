"""Billing / checkout logic tests (authoritative server-side pricing)."""
from decimal import Decimal

from extensions import db
from models import Sale, StockMovement
from tests.conftest import ADMIN_PASSWORD, CASHIER_PASSWORD


def test_checkout_prices_from_db_and_deducts_stock(client, login, app):
    login("cashier", CASHIER_PASSWORD)
    seed = app.config["SEED"]
    response = client.post(
        "/billing/checkout",
        json={
            "items": [{"product_id": seed["water_id"], "quantity": 2}],
            "payment_method": "cash",
            "amount_received": "100",
        },
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["grand_total"] == 50.00
    assert data["change_due"] == 50.00
    assert data["invoice_number"].startswith("INV-")

    from models import Product

    product = db.session.get(Product, seed["water_id"])
    assert product.stock_quantity == 98

    sale = db.session.get(Sale, data["sale_id"])
    assert sale.grand_total == Decimal("50.00")
    assert sale.payment_method == "cash"
    assert sale.movements.first().quantity_change == -2


def test_checkout_generates_invoice_and_refreshes_dashboard(client, login, app):
    login("cashier", CASHIER_PASSWORD)
    seed = app.config["SEED"]
    response = client.post(
        "/billing/checkout",
        json={
            "items": [{"product_id": seed["water_id"], "quantity": 1}],
            "payment_method": "cash",
            "amount_received": "25",
        },
    )
    assert response.status_code == 200
    data = response.get_json()

    invoice = client.get(data["invoice_url"])
    assert invoice.status_code == 200
    assert data["invoice_number"].encode() in invoice.data
    assert b"Spring Water" in invoice.data

    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.headers["Cache-Control"] == "no-store"
    assert b"1 bill(s) generated" in dashboard.data
    assert data["invoice_number"].encode() in dashboard.data
    assert b"\xe2\x82\xb925.00" in dashboard.data


def test_checkout_rounds_line_tax_the_same_as_pos(client, login, app):
    from models import Product

    login("cashier", CASHIER_PASSWORD)
    seed = app.config["SEED"]
    product = db.session.get(Product, seed["water_id"])
    product.selling_price = Decimal("0.02")
    product.discount_percent = Decimal("1.00")
    product.tax_rate = Decimal("25.00")
    db.session.commit()

    response = client.post(
        "/billing/checkout",
        json={
            "items": [{"product_id": seed["water_id"], "quantity": 1}],
            "payment_method": "cash",
            "amount_received": "0.03",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["grand_total"] == 0.03


def test_item_discount_and_bill_discount(client, login, app):
    login("cashier", CASHIER_PASSWORD)
    seed = app.config["SEED"]
    response = client.post(
        "/billing/checkout",
        json={
            "items": [{"product_id": seed["juice_id"], "quantity": 1}],
            "payment_method": "cash",
            "amount_received": "200",
            "bill_discount_percent": "10",
        },
    )
    assert response.status_code == 200
    data = response.get_json()
    # Juice: 90 - 10% = 81; bill discount 10% => 72.90
    assert data["grand_total"] == 72.90


def test_insufficient_stock_is_rejected(client, login, app):
    login("cashier", CASHIER_PASSWORD)
    seed = app.config["SEED"]
    response = client.post(
        "/billing/checkout",
        json={"items": [{"product_id": seed["juice_id"], "quantity": 6}]},
    )
    assert response.status_code == 400
    assert response.get_json()["success"] is False
    assert "stock" in response.get_json()["message"].lower()

    from models import Product

    product = db.session.get(Product, seed["juice_id"])
    assert product.stock_quantity == 5


def test_client_token_makes_checkout_idempotent(client, login, app):
    login("cashier", CASHIER_PASSWORD)
    seed = app.config["SEED"]
    payload = {
        "items": [{"product_id": seed["water_id"], "quantity": 1}],
        "payment_method": "card",
        "client_token": "token-abc",
    }
    first = client.post("/billing/checkout", json=payload)
    second = client.post("/billing/checkout", json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.get_json()["sale_id"] == second.get_json()["sale_id"]

    from models import Product

    product = db.session.get(Product, seed["water_id"])
    assert product.stock_quantity == 99


def test_cash_payment_less_than_total_is_rejected(client, login, app):
    login("cashier", CASHIER_PASSWORD)
    seed = app.config["SEED"]
    response = client.post(
        "/billing/checkout",
        json={
            "items": [{"product_id": seed["water_id"], "quantity": 2}],
            "payment_method": "cash",
            "amount_received": "10",
        },
    )
    assert response.status_code == 400
    assert "less than" in response.get_json()["message"].lower()


def test_empty_cart_is_rejected(client, login):
    login("cashier", CASHIER_PASSWORD)
    response = client.post("/billing/checkout", json={"items": [], "payment_method": "cash"})
    assert response.status_code == 400
    assert "empty" in response.get_json()["message"].lower()


def test_invalid_payment_method_is_rejected(client, login, app):
    login("cashier", CASHIER_PASSWORD)
    seed = app.config["SEED"]
    response = client.post(
        "/billing/checkout",
        json={"items": [{"product_id": seed["water_id"], "quantity": 1}], "payment_method": "bitcoin"},
    )
    assert response.status_code == 400
    assert "payment" in response.get_json()["message"].lower()


def test_cashier_only_sees_own_sales(client, login, app):
    login("cashier", CASHIER_PASSWORD)
    seed = app.config["SEED"]
    client.post(
        "/billing/checkout",
        json={"items": [{"product_id": seed["water_id"], "quantity": 1}], "payment_method": "cash", "amount_received": 25},
    )
    response = client.get("/billing/sales")
    assert response.status_code == 200

    assert Sale.query.filter(Sale.cashier_id == seed["admin_id"]).count() == 0