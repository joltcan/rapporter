from flask import Blueprint

incidents_bp = Blueprint("incidents", __name__, template_folder="../templates/incidents")

from app.incidents import routes  # noqa: F401, E402
