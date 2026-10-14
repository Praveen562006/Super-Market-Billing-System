"""Stock adjustment and movement history tests."""
from extensions import db
from models import Product, StockMovement
from tests.conftest import ADMIN_PASSWORD, CASHIER_PASSWORD


def test_admin_adjusts_stock_and_logs_movement(client, login, app):
    login("admin", ADMIN_PASSWORD)
    seed = app.config["SEED"]
    response = client.post(
        f"/inventory/{seed['water_id']}/adjust",
        data={"quantity_change": "15", "reason": "Routine restock"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    product = db.session.get(Product, seed["water_id"])
    assert product.stock_quantity == 115
    movement = (
        StockMovement.query.filter_by(product_id=seed["water_id"])
        .order_by(StockMovement.id.desc())
        .first()
    )
    assert movement.quantity_change == 15
    assert movement.movement_type == "purchase"
    assert movement.reason == "Routine restock"
    assert movement.balance_after == 115


def test_adjustment_requires_reason(client, login, app):
    login("admin", ADMIN_PASSWORD)
    seed = app.config["SEED"]
    response = client.post(
        f"/inventory/{seed['water_id']}/adjust",
        data={"quantity_change": "5", "reason": ""},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"reason" in response.data
    product = db.session.get(Product, seed["water_id"])
    assert product.stock_quantity == 100


def test_cashier_cannot_adjust_stock(client, login):
    login("cashier", CASHIER_PASSWORD)
    response = client.post(
        "/inventory/1/adjust",
        data={"quantity_change": "5", "reason": "nope"},
    )
    assert response.status_code == 403