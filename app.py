"""Application factory and entry point."""
import os
from decimal import Decimal, InvalidOperation

from flask import Flask, render_template

from config import config, get_config
from extensions import db, login_manager, csrf


def _currency():
    from services.settings_service import get_currency_symbol

    return get_currency_symbol()


def register_filters(app):
    """Register the Jinja filters used across the templates."""

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


def create_app(config_class=None):
    app = Flask(__name__)

    if config_class is None:
        config_class = config
    else:
        config_class = get_config(config_class)
    app.config.from_object(config_class)

    # Ensure instance folder exists
    os.makedirs(app.instance_path, exist_ok=True)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Register template filters (money, number, datetime, date)
    register_filters(app)

    # Register blueprints
    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.billing import billing_bp
    from routes.products import products_bp
    from routes.inventory import inventory_bp
    from routes.reports import reports_bp
    from routes.users import users_bp
    from routes.settings import settings_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(billing_bp, url_prefix="/billing")
    app.register_blueprint(products_bp, url_prefix="/products")
    app.register_blueprint(inventory_bp, url_prefix="/inventory")
    app.register_blueprint(reports_bp, url_prefix="/reports")
    app.register_blueprint(users_bp, url_prefix="/users")
    app.register_blueprint(settings_bp, url_prefix="/settings")

    # Inject store info into all templates
    from services.settings_service import get_store_info

    @app.context_processor
    def inject_store():
        return {"store": get_store_info()}

    # Redirect root to dashboard
    from flask import redirect, url_for
    from flask_login import current_user

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard.index"))
        return redirect(url_for("auth.login"))

    # Error handlers
    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(e):
        db.session.rollback()
        return render_template("errors/500.html"), 500

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host=app.config.get("HOST", "127.0.0.1"), port=app.config.get("PORT", 5000))
