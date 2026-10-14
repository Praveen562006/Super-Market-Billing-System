"""Access to configurable store settings.

Settings are stored in the ``settings`` table and fall back to the values in
``config.py`` (which in turn read the environment).  This makes store name,
currency, tax rate and discount policy configurable at runtime without code
changes.
"""
from decimal import Decimal, InvalidOperation

from flask import current_app, g

from extensions import db
from models import Setting

# Keys that may be edited from the Settings screen and their config fallback.
EDITABLE_KEYS = (
    "STORE_NAME",
    "STORE_ADDRESS",
    "STORE_PHONE",
    "STORE_EMAIL",
    "STORE_GSTIN",
    "CURRENCY_SYMBOL",
    "DEFAULT_TAX_RATE",
    "DEFAULT_LOW_STOCK_THRESHOLD",
    "MAX_BILL_DISCOUNT_PERCENT",
    "INVOICE_PREFIX",
)

LABELS = {
    "STORE_NAME": "Store name",
    "STORE_ADDRESS": "Address",
    "STORE_PHONE": "Phone",
    "STORE_EMAIL": "Email",
    "STORE_GSTIN": "Tax / GSTIN number",
    "CURRENCY_SYMBOL": "Currency symbol",
    "DEFAULT_TAX_RATE": "Default tax rate (%)",
    "DEFAULT_LOW_STOCK_THRESHOLD": "Default low-stock threshold",
    "MAX_BILL_DISCOUNT_PERCENT": "Maximum bill discount (%)",
    "INVOICE_PREFIX": "Invoice number prefix",
}

DEFAULTS = {
    "INVOICE_PREFIX": "INV",
    "DEFAULT_TAX_RATE": "0",
    "DEFAULT_LOW_STOCK_THRESHOLD": "10",
    "MAX_BILL_DISCOUNT_PERCENT": "100",
    "CURRENCY_SYMBOL": "\u20b9",
}


def _cache():
    cache = getattr(g, "_settings_cache", None)
    if cache is None:
        cache = {}
        g._settings_cache = cache
    return cache


def get_setting(key, default=None):
    """Return the configured value for *key* or the config/default fallback.

    Values are cached per application/request context to avoid repeated
    queries when formatting many prices.
    """
    cache = _cache()
    if key in cache:
        return cache[key]
    row = db.session.get(Setting, key)
    if row is not None and row.value not in (None, ""):
        value = row.value
    elif default is not None:
        value = default
    elif key in DEFAULTS:
        value = DEFAULTS[key]
    else:
        value = current_app.config.get(key, "")
    cache[key] = value
    return value


def set_setting(key, value):
    row = db.session.get(Setting, key)
    if row is None:
        row = Setting(key=key)
        db.session.add(row)
    row.value = "" if value is None else str(value)
    _cache()[key] = row.value
    return row


def get_decimal_setting(key, default="0"):
    try:
        return Decimal(str(get_setting(key, default)))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(str(default))


def get_int_setting(key, default=0):
    try:
        return int(str(get_setting(key, default)).strip())
    except (TypeError, ValueError):
        return default


def get_default_tax_rate():
    return get_decimal_setting("DEFAULT_TAX_RATE", "0")


def get_max_bill_discount():
    return get_decimal_setting("MAX_BILL_DISCOUNT_PERCENT", "100")


def get_default_low_stock_threshold():
    return get_int_setting("DEFAULT_LOW_STOCK_THRESHOLD", 10)


def get_currency_symbol():
    return get_setting("CURRENCY_SYMBOL", "\u20b9")


def get_store_info():
    return {
        "name": get_setting("STORE_NAME", "SuperMarket"),
        "address": get_setting("STORE_ADDRESS", ""),
        "phone": get_setting("STORE_PHONE", ""),
        "email": get_setting("STORE_EMAIL", ""),
        "gstin": get_setting("STORE_GSTIN", ""),
        "currency": get_currency_symbol(),
    }


def all_settings():
    return {key: get_setting(key, DEFAULTS.get(key, current_app.config.get(key, "")))
            for key in EDITABLE_KEYS}


def ensure_defaults():
    """Create missing setting rows from config (called during init)."""
    from flask import current_app

    for key in EDITABLE_KEYS:
        fallback = DEFAULTS.get(key, current_app.config.get(key, ""))
        if db.session.get(Setting, key) is None and fallback not in (None, ""):
            db.session.add(Setting(key=key, value=str(fallback)))
    db.session.commit()
