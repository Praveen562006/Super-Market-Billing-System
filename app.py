"""Application factory and entry point.

Run locally with::

    python app.py

The application is deliberately split into small blueprints and a service
layer.  See ``README.md`` for setup instructions.
"""
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path

from flask import Flask, render_template

from config import config_map
from extensions import csrf, db, login_manager
from models import User
from utils import utcnow

# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------
def _currency():
    from services.settings_service import get_currency_symbol

    return get_currency_symbol()


def register_filters(app):
    @app.template_filter("money")
    def money_filter(value):
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return value
        return f"{_currency()}{amount:,.2f}"

    @app.template_filter("number")
    def number_filter(value):
        try:
            return f"{Decimal(str(value)):,.2f}"
        except (InvalidOperation, TypeError, ValueError):
            return value

    @app.template_filter("datetime")
    def datetime_filter(value, fmt="%Y-%m-%d %H:%M"):
        if not value:
            return "-"
        return value.strftime(fmt)

    @app.template_filter("date")
    def date_filter(value, fmt="%Y-%m-%d"):
        if not value:
            return "-"
        return value.strftime(fmt)


def register_context(app):
    from services.settings_service import get_store_info

    @app.context_processor
    def inject_globals():
        return {
            "store": get_store_info(),
            "current_year": utcnow().year,
        }


def register_error_handlers(app):
    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(_error):
        db.session.rollback()
        return render_template("errors/500.html"), 500


def register_blueprints(app):
    from routes.auth import auth_bp
    from routes.billing import billing_bp
    from routes.dashboard import dashboard_bp
    from routes.inventory import inventory_bp
    from routes.products import products_bp
    from routes.reports import reports_bp
    from routes.settings import settings_bp
    from routes.users import users_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(products_bp, url_prefix="/products")
    app.register_blueprint(billing_bp, url_prefix="/billing")
    app.register_blueprint(inventory_bp, url_prefix="/inventory")
    app.register_blueprint(reports_bp, url_prefix="/reports")
    app.register_blueprint(users_bp, url_prefix="/users")
    app.register_blueprint(settings_bp, url_prefix="/settings")


def create_app(config_name=None):
    app = Flask(__name__, instance_relative_config=True)
    config_name = config_name or os.environ.get("FLASK_ENV", "development")
    app.config.from_object(config_map.get(config_name, config_map["default"]))

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None

    register_filters(app)
    register_context(app)
    register_error_handlers(app)
    register_blueprints(app)

    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net data:; "
            "img-src 'self' data:; "
            "connect-src 'self';",
        )
        return response

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host=app.config["HOST"], port=app.config["PORT"], debug=app.config["DEBUG"])
