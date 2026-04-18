"""Application factory for the Scout ticket system."""

import os
from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv

load_dotenv()

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=[])


def _bool_env(name, default=False):
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def create_app():
    app = Flask(__name__)

    # --- Config -----------------------------------------------------------
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL", "postgresql://rapporter:rapporter@localhost:5432/rapporter"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

    # Session cookies: Secure flag defaults to whatever SESSION_COOKIE_SECURE
    # is set to in the environment, with FLASK_ENV=production as a fallback
    # on. The site is designed to work over plain HTTP during camps without
    # internet, so this MUST be easy to turn off.
    is_prod = os.environ.get("FLASK_ENV", "production") == "production"
    secure_default = is_prod and not _bool_env("ALLOW_INSECURE_COOKIES", False)
    app.config["SESSION_COOKIE_SECURE"] = _bool_env("SESSION_COOKIE_SECURE", secure_default)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["REMEMBER_COOKIE_SECURE"] = app.config["SESSION_COOKIE_SECURE"]
    app.config["REMEMBER_COOKIE_HTTPONLY"] = True
    app.config["WTF_CSRF_ENABLED"] = True

    # Base URL for QR codes (absolute links that devices scan).
    app.config["BASE_URL"] = os.environ.get("BASE_URL", "http://localhost")

    # --- Extensions -------------------------------------------------------
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    # Login-required flash messages go through i18n at render time; keep
    # this as the English source so detect_locale() can pick the right
    # translation.
    login_manager.login_message = "Please sign in to continue."
    login_manager.login_message_category = "warning"

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return User.query.get(int(user_id))

    # --- i18n -------------------------------------------------------------
    from app import i18n
    i18n.init_app(app)

    # --- Blueprints -------------------------------------------------------
    from app.auth import auth_bp
    from app.admin import admin_bp
    from app.tickets import tickets_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(tickets_bp, url_prefix="/tickets")

    # --- Root redirect ----------------------------------------------------
    @app.route("/")
    def index():
        if current_user.is_authenticated:
            if current_user.is_admin:
                return redirect(url_for("admin.dashboard"))
            return redirect(url_for("tickets.list_tickets"))
        return redirect(url_for("auth.login"))

    register_commands(app)
    return app


def register_commands(app):
    """CLI: `flask seed` creates the default admin account on first boot.

    Idempotent -- safe to re-run."""
    import click

    @app.cli.command("seed")
    def seed():
        from app.models import User, ROLE_ADMIN
        import bcrypt

        admin = User.query.filter_by(username="sysadm").first()
        if not admin:
            pwd_hash = bcrypt.hashpw("ninja01".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            admin = User(username="sysadm", password_hash=pwd_hash, role=ROLE_ADMIN)
            db.session.add(admin)
            db.session.commit()
            click.echo("Admin user 'sysadm' created (password: ninja01).")
        else:
            click.echo("Admin user 'sysadm' already exists.")
