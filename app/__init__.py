import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
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


def create_app():
    app = Flask(__name__)

    # Configuration
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL", "postgresql://rapporter:rapporter@localhost:5432/rapporter"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

    # Security settings
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("FLASK_ENV", "production") == "production"
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["REMEMBER_COOKIE_SECURE"] = os.environ.get("FLASK_ENV", "production") == "production"
    app.config["REMEMBER_COOKIE_HTTPONLY"] = True
    app.config["WTF_CSRF_ENABLED"] = True

    # Base URL for QR codes
    app.config["BASE_URL"] = os.environ.get("BASE_URL", "https://localhost")

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)

    # Login manager
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Logga in för att fortsätta."
    login_manager.login_message_category = "warning"

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return User.query.get(int(user_id))

    # Register blueprints
    from app.auth import auth_bp
    from app.admin import admin_bp
    from app.incidents import incidents_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(incidents_bp, url_prefix="/incidents")

    # Root redirect
    from flask import redirect, url_for
    from flask_login import current_user

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            if current_user.role == "admin":
                return redirect(url_for("admin.dashboard"))
            return redirect(url_for("incidents.list_incidents"))
        return redirect(url_for("auth.login"))

    # Register seed command
    register_commands(app)

    return app


def register_commands(app):
    import click

    @app.cli.command("seed")
    def seed():
        """Seed the database with initial data."""
        from app.models import User, Camp
        import bcrypt

        # Create admin user if not exists
        admin = User.query.filter_by(username="sysadm").first()
        if not admin:
            password_hash = bcrypt.hashpw("ninja01".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            admin = User(
                username="sysadm",
                password_hash=password_hash,
                role="admin",
            )
            db.session.add(admin)
            db.session.commit()
            click.echo("Admin-användare 'sysadm' skapad.")
        else:
            click.echo("Admin-användare 'sysadm' finns redan.")
