"""Small validation/parsing helpers shared by the routes."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation


def utcnow():
    """Return the current UTC time as a *naive* datetime.

    ``datetime.utcnow()`` is deprecated from Python 3.12; this uses a
    timezone-aware clock instead and strips the tzinfo so the result stays
    compatible with the naive datetimes stored in the database.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ValidationError(Exception):
    """Raised by the helpers below; the message is safe to show to users."""


def clean_str(value, max_length=None, default=""):
    value = (value or "").strip()
    if max_length and len(value) > max_length:
        raise ValidationError(f"Value is longer than {max_length} characters.")
    return value or default


def parse_decimal(value, field, minimum=None, maximum=None, required=True, default=None):
    if value in (None, ""):
        if required:
            raise ValidationError(f"{field} is required.")
        return default
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ValidationError(f"{field} must be a valid number.")
    if minimum is not None and number < minimum:
        raise ValidationError(f"{field} must be at least {minimum}.")
    if maximum is not None and number > maximum:
        raise ValidationError(f"{field} must be at most {maximum}.")
    return number


def parse_int(value, field, minimum=None, maximum=None, required=True, default=None):
    if value in (None, ""):
        if required:
            raise ValidationError(f"{field} is required.")
        return default
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be a whole number.")
    if minimum is not None and number < minimum:
        raise ValidationError(f"{field} must be at least {minimum}.")
    if maximum is not None and number > maximum:
        raise ValidationError(f"{field} must be at most {maximum}.")
    return number


def parse_date(value, field, required=False, default=None):
    if not value:
        if required:
            raise ValidationError(f"{field} is required.")
        return default
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValidationError(f"{field} must be a valid date (YYYY-MM-DD).")


def parse_optional_id(value):
    if value in (None, "", "0"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
