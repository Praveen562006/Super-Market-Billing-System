"""Authentication flow tests."""
from tests.conftest import ADMIN_PASSWORD, CASHIER_PASSWORD


def test_login_page_renders(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert b"Sign in" in response.data or b"Login" in response.data or b"login" in response.data


def test_login_required_redirects_anonymous(client):
    response = client.get("/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_login_succeeds_for_admin(client, login):
    response = login("admin", ADMIN_PASSWORD)
    assert response.status_code == 200
    with client.session_transaction() as session:
        assert session.get("_user_id") is not None


def test_login_rejects_bad_password(client, login):
    response = login("admin", "wrong-password")
    assert response.status_code == 401
    assert b"Invalid username or password" in response.data


def test_login_rejects_disabled_account(client, login):
    response = login("disabled", CASHIER_PASSWORD)
    assert response.status_code == 403
    assert b"disabled" in response.data.lower()


def test_logout(client, login):
    login("admin", ADMIN_PASSWORD)
    response = client.post("/logout", follow_redirects=True)
    assert response.status_code == 200
    with client.session_transaction() as session:
        assert session.get("_user_id") is None
