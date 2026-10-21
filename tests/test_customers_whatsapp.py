"""Registered-buyer lookup and WhatsApp bill delivery tests."""
from models import Customer
from tests.conftest import CASHIER_PASSWORD


def _checkout(client, app, **extra):
    seed = app.config["SEED"]
    payload = {
        "items": [{"product_id": seed["water_id"], "quantity": 1}],
        "payment_method": "cash",
        "amount_received": "25",
    }
    payload.update(extra)
    return client.post("/billing/checkout", json=payload)


def test_checkout_registers_buyer_and_lookup_returns_name(client, login, app):
    login("cashier", CASHIER_PASSWORD)
    response = _checkout(client, app, customer_mobile="98765 43210", customer_name="Ravi Kumar")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    # The local number gets the configured country code (91) for wa.me.
    assert data["whatsapp_url"].startswith("https://wa.me/919876543210")

    customer = Customer.query.filter_by(mobile="9876543210").first()
    assert customer is not None
    assert customer.name == "Ravi Kumar"

    lookup = client.get("/billing/customers/lookup?mobile=9876543210")
    assert lookup.status_code == 200
    assert lookup.get_json() == {"found": True, "name": "Ravi Kumar", "mobile": "9876543210"}


def test_lookup_unknown_number(client, login):
    login("cashier", CASHIER_PASSWORD)
    response = client.get("/billing/customers/lookup?mobile=9000000000")
    assert response.status_code == 200
    assert response.get_json() == {"found": False}


def test_checkout_without_mobile_has_no_whatsapp_link(client, login, app):
    login("cashier", CASHIER_PASSWORD)
    response = _checkout(client, app)
    assert response.status_code == 200
    assert response.get_json()["whatsapp_url"] is None
    assert Customer.query.count() == 0


def test_returning_buyer_name_is_refreshed(client, login, app):
    login("cashier", CASHIER_PASSWORD)
    _checkout(client, app, customer_mobile="9876543210", customer_name="First Name")
    _checkout(client, app, customer_mobile="9876543210", customer_name="Updated Name")
    assert Customer.query.count() == 1
    assert Customer.query.first().name == "Updated Name"


def test_invoice_shows_whatsapp_button(client, login, app):
    login("cashier", CASHIER_PASSWORD)
    data = _checkout(client, app, customer_mobile="9876543210", customer_name="Ravi").get_json()
    invoice = client.get(data["invoice_url"])
    assert invoice.status_code == 200
    assert b"Send on WhatsApp" in invoice.data

    plain = _checkout(client, app).get_json()
    invoice_plain = client.get(plain["invoice_url"])
    assert b"Send on WhatsApp" not in invoice_plain.data


def test_customer_lookup_requires_login(client):
    response = client.get("/billing/customers/lookup?mobile=9876543210")
    assert response.status_code == 302
