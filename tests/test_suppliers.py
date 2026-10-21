"""Supplier directory management tests (admin only CRUD)."""
from extensions import db
from models import Supplier


def _form(**overrides):
    data = {
        "name": "Acme Distributors",
        "contact_person": "Ravi",
        "phone": "9876543210",
        "email": "acme@example.com",
        "address": "1 Market Road",
        "gstin": "29ABCDE1234F1Z5",
        "notes": "Weekly delivery",
        "is_active": "on",
    }
    data.update(overrides)
    return data


def test_admin_creates_and_lists_supplier(client, login):
    login("admin")
    response = client.post("/suppliers/new", data=_form(), follow_redirects=True)
    assert response.status_code == 200
    assert b"Acme Distributors" in response.data

    supplier = Supplier.query.filter_by(name="Acme Distributors").first()
    assert supplier is not None
    assert supplier.contact_person == "Ravi"
    assert supplier.is_active is True


def test_supplier_name_is_required(client, login):
    login("admin")
    response = client.post("/suppliers/new", data=_form(name=""), follow_redirects=True)
    assert response.status_code == 200
    assert Supplier.query.count() == 0
    assert b"required" in response.data.lower()


def test_admin_edits_and_deactivates_supplier(client, login):
    login("admin")
    client.post("/suppliers/new", data=_form(), follow_redirects=True)
    supplier = Supplier.query.first()

    client.post(f"/suppliers/{supplier.id}/edit", data=_form(name="Acme Wholesale"), follow_redirects=True)
    assert db.session.get(Supplier, supplier.id).name == "Acme Wholesale"

    client.post(f"/suppliers/{supplier.id}/toggle", follow_redirects=True)
    assert db.session.get(Supplier, supplier.id).is_active is False


def test_supplier_can_be_deleted(client, login):
    login("admin")
    client.post("/suppliers/new", data=_form(), follow_redirects=True)
    supplier = Supplier.query.first()
    client.post(f"/suppliers/{supplier.id}/delete", follow_redirects=True)
    assert Supplier.query.count() == 0
