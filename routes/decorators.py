"""Reusable authorization decorators."""
from functools import wraps

from flask import abort
from flask_login import current_user, login_required


def admin_required(view):
    """Allow only authenticated administrators."""

    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def role_required(*roles):
    """Allow only authenticated users whose role is in *roles*."""

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator
