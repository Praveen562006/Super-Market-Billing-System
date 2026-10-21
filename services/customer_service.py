"""Registered buyers ("customers") keyed by their mobile / WhatsApp number.

The POS uses :func:`find_by_mobile` to auto-fill a returning customer's name,
and :func:`register` to remember a customer the first time they buy something.
"""
from extensions import db
from models import Customer
from services import settings_service


def normalize_mobile(value):
    """Return the digits of *value* (dropping spaces, dashes and ``+``)."""
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits[:20] or None


def find_by_mobile(mobile):
    """Look up a registered buyer by mobile number.

    Matches the exact stored digits, and — when a bare 10-digit local number
    is supplied — also tries it prefixed with the configured country code.
    """
    digits = normalize_mobile(mobile)
    if not digits:
        return None

    customer = Customer.query.filter(Customer.mobile == digits).first()
    if customer is not None:
        return customer

    country_code = settings_service.get_whatsapp_country_code()
    if country_code and len(digits) == 10:
        return Customer.query.filter(Customer.mobile == f"{country_code}{digits}").first()
    return None


def register(mobile, name=None, email=None):
    """Create or update the registered buyer for *mobile* (no commit)."""
    digits = normalize_mobile(mobile)
    if not digits:
        return None

    customer = Customer.query.filter(Customer.mobile == digits).first()
    if customer is None:
        customer = Customer(mobile=digits, name=(name or None), email=(email or None))
        db.session.add(customer)
    else:
        if name:
            customer.name = name
        if email:
            customer.email = email
    return customer
