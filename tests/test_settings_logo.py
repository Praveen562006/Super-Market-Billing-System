"""Store settings, logo upload and invoice PDF tests."""
import base64
import io

from extensions import db
from models import Setting
from services.settings_service import get_logo_path

# A real 1x1 transparent PNG (valid image data).
VALID_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def _settings_form(**overrides):
    data = {
        "STORE_NAME": "Test Store",
        "STORE_ADDRESS": "1 Test Road",
        "STORE_PHONE": "0401234567",
        "STORE_EMAIL": "store@example.com",
        "STORE_GSTIN": "36AAAAA0000A1Z5",
        "CURRENCY_SYMBOL": "\u20b9",
        "DEFAULT_TAX_RATE": "5",
        "DEFAULT_LOW_STOCK_THRESHOLD": "10",
        "MAX_BILL_DISCOUNT_PERCENT": "100",
        "INVOICE_PREFIX": "INV",
        "WHATSAPP_COUNTRY_CODE": "91",
    }
    data.update(overrides)
    return data


def _png():
    return io.BytesIO(VALID_PNG)


def test_admin_uploads_logo(client, login):
    login("admin")
    data = _settings_form()
    data["logo"] = (_png(), "brand.png")
    response = client.post(
        "/settings/", data=data, content_type="multipart/form-data", follow_redirects=True
    )
    assert response.status_code == 200

    path = get_logo_path()
    assert path.startswith("uploads/logo_")
    assert path.endswith(".png")


def test_logo_rejects_unsupported_extension(client, login):
    login("admin")
    data = _settings_form()
    data["logo"] = (io.BytesIO(b"nope"), "brand.txt")
    response = client.post(
        "/settings/", data=data, content_type="multipart/form-data", follow_redirects=True
    )
    assert response.status_code == 200
    assert b"Unsupported logo format" in response.data
    assert get_logo_path() == ""


def test_logo_can_be_removed(client, login):
    login("admin")
    data = _settings_form()
    data["logo"] = (_png(), "brand.png")
    client.post("/settings/", data=data, content_type="multipart/form-data", follow_redirects=True)
    assert get_logo_path() != ""

    client.post(
        "/settings/",
        data=_settings_form(remove_logo="1"),
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert get_logo_path() == ""


def test_whatsapp_country_code_is_saved(client, login):
    login("admin")
    client.post(
        "/settings/",
        data=_settings_form(WHATSAPP_COUNTRY_CODE="44"),
        follow_redirects=True,
    )
    assert db.session.get(Setting, "WHATSAPP_COUNTRY_CODE").value == "44"


def _checkout(client, app):
    seed = app.config["SEED"]
    return client.post(
        "/billing/checkout",
        json={
            "items": [{"product_id": seed["water_id"], "quantity": 1}],
            "payment_method": "card",
        },
    ).get_json()


def test_invoice_pdf_renders_with_and_without_logo(client, login, app):
    login("admin")
    first = _checkout(client, app)
    pdf = client.get(f"/billing/sales/{first['sale_id']}/pdf")
    assert pdf.status_code == 200
    assert pdf.data.startswith(b"%PDF")

    data = _settings_form()
    data["logo"] = (_png(), "brand.png")
    client.post("/settings/", data=data, content_type="multipart/form-data", follow_redirects=True)
    assert get_logo_path() != ""

    second = _checkout(client, app)
    pdf_with_logo = client.get(f"/billing/sales/{second['sale_id']}/pdf")
    assert pdf_with_logo.status_code == 200
    assert pdf_with_logo.data.startswith(b"%PDF")
