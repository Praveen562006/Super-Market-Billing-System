"""Role-based access control tests."""
from tests.conftest import ADMIN_PASSWORD, CASHIER_PASSWORD

ADMIN_ONLY_PATHS = ["/products/", "/suppliers/", "/inventory/", "/reports/", "/users/", "/settings/"]


def test_cashier_is_denied_admin_pages(client, login):
    login("cashier", CASHIER_PASSWORD)
    for path in ADMIN_ONLY_PATHS:
        assert client.get(path).status_code == 403, path


def test_admin_can_open_admin_pages(client, login):
    login("admin", ADMIN_PASSWORD)
    for path in ADMIN_ONLY_PATHS:
        assert client.get(path).status_code == 200, path


def test_cashier_can_open_pos(client, login):
    login("cashier", CASHIER_PASSWORD)
    assert client.get("/").status_code == 200
    assert client.get("/billing/").status_code == 200
