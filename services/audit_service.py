"""Audit logging for important administrative and business actions."""
from flask import has_request_context, request
from flask_login import current_user

from extensions import db
from models import AuditLog


def _current_user_id():
    try:
        if current_user and current_user.is_authenticated:
            return current_user.id
    except Exception:  # pragma: no cover - defensive
        pass
    return None


def _current_ip():
    if has_request_context():
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.remote_addr
    return None


def log_action(action, entity=None, entity_id=None, details=None, user_id=None, commit=False):
    """Record an audit entry.

    By default the entry joins the caller's transaction (not committed here)
    so that, for example, a sale and its audit trail are committed together.
    """
    entry = AuditLog(
        user_id=user_id if user_id is not None else _current_user_id(),
        action=action,
        entity=entity,
        entity_id=str(entity_id) if entity_id is not None else None,
        details=details,
        ip_address=_current_ip(),
    )
    db.session.add(entry)
    if commit:
        db.session.commit()
    return entry
