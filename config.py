"""Application configuration.

Values are read from environment variables (optionally loaded from a local
``.env`` file).  Nothing secret is hard-coded here; sensible *development*
defaults are provided so the project runs locally out of the box, but the
``SECRET_KEY`` and any production credentials must come from the environment.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"

# Load a local .env file if present (does not override real env vars).
load_dotenv(BASE_DIR / ".env")


def _bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class Config:
    """Base configuration shared by all environments."""

    # --- Core -----------------------------------------------------
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-secret-change-me")
    DEBUG = _bool(os.environ.get("FLASK_DEBUG"), default=False)
    TESTING = False

    HOST = os.environ.get("HOST", "127.0.0.1")
    PORT = int(os.environ.get("PORT", "5000"))

    # --- Database ------------------------------------------------
    # Default to a SQLite file inside ./instance.  A custom DATABASE_URL
    # (e.g. MySQL) can be supplied through the environment.  The code uses
    # the SQLAlchemy ORM exclusively so switching backends requires no
    # query changes.
    _default_sqlite = "sqlite:///" + str((INSTANCE_DIR / "supermarket.db").as_posix())
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or _default_sqlite
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        # `timeout` helps avoid "database is locked" errors under SQLite.
        "connect_args": {"timeout": 30},
        "pool_pre_ping": True,
    }

    # --- Session / cookies --------------------------------------
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Enable when serving over HTTPS.
    SESSION_COOKIE_SECURE = _bool(os.environ.get("SESSION_COOKIE_SECURE"), default=False)
    PERMANENT_SESSION_LIFETIME = int(os.environ.get("SESSION_LIFETIME", "43200"))  # 12h

    # --- CSRF -----------------------------------------------------
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None

    # --- Branding / business rules -------------------------------
    STORE_NAME = os.environ.get("STORE_NAME", "SuperMarket")
    STORE_ADDRESS = os.environ.get("STORE_ADDRESS", "123 Main Street, Your City")
    STORE_PHONE = os.environ.get("STORE_PHONE", "+00 000 000 0000")
    STORE_EMAIL = os.environ.get("STORE_EMAIL", "contact@example.com")
    STORE_GSTIN = os.environ.get("STORE_GSTIN", "")
    CURRENCY_SYMBOL = os.environ.get("CURRENCY_SYMBOL", "\u20b9")

    DEFAULT_TAX_RATE = os.environ.get("DEFAULT_TAX_RATE", "0")
    DEFAULT_LOW_STOCK_THRESHOLD = int(os.environ.get("DEFAULT_LOW_STOCK_THRESHOLD", "10"))
    MAX_BILL_DISCOUNT_PERCENT = os.environ.get("MAX_BILL_DISCOUNT_PERCENT", "100")

    # Initial administrator bootstrap (permissions only; password should
    # be generated if not supplied).
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
    ADMIN_NAME = os.environ.get("ADMIN_NAME", "Store Administrator")


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "testing-secret-key"


config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
