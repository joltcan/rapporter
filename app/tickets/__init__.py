from flask import Blueprint

tickets_bp = Blueprint("tickets", __name__, template_folder="../templates/tickets")

from app.tickets import routes  # noqa: F401, E402
