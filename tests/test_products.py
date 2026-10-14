"""Product and category management tests."""
from extensions import db
from models import Product


def _form(**overrides):
    data = {
        "sku": "SKU-9000",
        "name": "Test Product",
        "selling_price": "50.00",
        "cost_price": "30.00",
        "discount_percent": "5",
        "tax_rate": "",
        "low_stock_threshold": "5",
        "stock_quantity": "20",
        "is_active": "on",
    }
    data.update(overrides)
    return data


def test_admin_creates_product_with_opening_stock(client, login, app):
    login("admin")
    response = client.post("/products/new", data=_form(), follow_redirects=True)
    assert response.status_code == 200

    product = Product.query.filter_by(sku="SKU-9000").first()
    assert product is not None
    assert product.stock_quantity == 20
    assert product.movements.count() == 1
    assert product.movements.first().movement_type == "purchase"


def test_duplicate_sku_is_rejected(client, login, app):
    login("admin")
    client.post("/products/new", data=_form(sku="SKU-DUP"), follow_redirects=True)
    before = Product.query.count()
    response = client.post("/products/new", data=_form(sku="SKU-DUP", name="Other"), follow_redirects=True)
    assert response.status_code == 200
    assert Product.query.count() == before
    assert b"already exists" in response.data


def test_missing_name_is_rejected(client, login):
    login("admin")
    response = client.post("/products/new", data=_form(sku="SKU-X", name=""), follow_redirects=True)
    assert b"name is required" in response.data
    assert Product.query.filter_by(sku="SKU-X").first() is None


def test_deleting_referenced_product_deactivates_it(client, login, app):
    login("admin")
    seed = app.config["SEED"]
    client.post(
        "/billing/checkout",
        json={"items": [{"product_id": seed["water_id"], "quantity": 1}], "payment_method": "cash", "amount_received": 25},
    )
    response = client.post(f"/products/{seed['water_id']}/delete", follow_redirects=True)
    assert response.status_code == 200
    product = db.session.get(Product, seed["water_id"])
    assert product is not None
    assert product.is_active is False
