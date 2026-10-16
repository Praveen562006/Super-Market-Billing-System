"""Environment-based configuration for the SuperMarket Billing System."""
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Base configuration."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'supermarket.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Store settings
    STORE_NAME = os.environ.get("STORE_NAME", "SuperMarket")
    STORE_ADDRESS = os.environ.get("STORE_ADDRESS", "")
    STORE_PHONE = os.environ.get("STORE_PHONE", "")
    STORE_EMAIL = os.environ.get("STORE_EMAIL", "")
    STORE_GSTIN = os.environ.get("STORE_GSTIN", "")
    CURRENCY_SYMBOL = os.environ.get("CURRENCY_SYMBOL", "\u20b9")

    # Billing defaults
    DEFAULT_TAX_RATE = os.environ.get("DEFAULT_TAX_RATE", "0")
    DEFAULT_LOW_STOCK_THRESHOLD = os.environ.get("DEFAULT_LOW_STOCK_THRESHOLD", "10")
    MAX_BILL_DISCOUNT_PERCENT = os.environ.get("MAX_BILL_DISCOUNT_PERCENT", "100")
    INVOICE_PREFIX = os.environ.get("INVOICE_PREFIX", "INV")

    # Bootstrap admin
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
    ADMIN_NAME = os.environ.get("ADMIN_NAME", "Store Administrator")

    # Server settings
    HOST = os.environ.get("HOST", "127.0.0.1")
    PORT = int(os.environ.get("PORT", "5000"))


class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    DEBUG = False
    TESTING = False


class TestingConfig(Config):
    DEBUG = False
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test-secret-key"


# Map Flask_ENV to config class
_config_by_env = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def _resolve_config():
    env = os.environ.get("FLASK_ENV", "development").lower()
    return _config_by_env.get(env, DevelopmentConfig)


def get_config(name=None):
    """Resolve a configuration by name (``"development"``, ``"testing"`` ...).

    Passing ``None`` or an unknown name falls back to the environment-derived
    configuration. Non-string values (config classes/objects) are returned
    unchanged so callers may pass either form.
    """
    if name is None:
        return _resolve_config()
    if isinstance(name, str):
        return _config_by_env.get(name.lower(), _resolve_config())
    return name


config = _resolve_config()
