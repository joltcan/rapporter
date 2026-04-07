from datetime import datetime, timezone
from functools import wraps

from flask import (
    render_template, redirect, url_for, flash,
    request, abort, current_app,
)
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import (
    StringField, SelectField, TextAreaField, BooleanField,
    SubmitField, DateTimeLocalField, RadioField,
)
from wtforms.validators import DataRequired, Optional, Length

from app.incidents import incidents_bp
from app.models import Incident, Camp, User
from app import db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _get_active_camps():
    return Camp.query.filter_by(is_active=True).order_by(Camp.name).all()


# ---------------------------------------------------------------------------
# Incident form
# ---------------------------------------------------------------------------

class IncidentForm(FlaskForm):
    occurred_at = DateTimeLocalField(
        "Tidpunkt för händelsen",
        format="%Y-%m-%dT%H:%M",
        validators=[DataRequired(message="Ange tidpunkt.")],
    )
    camp_id = SelectField(
        "Läger",
        coerce=int,
        validators=[DataRequired(message="Välj ett läger.")],
    )
    involved_person = TextAreaField(
        "Inblandad person (namn, ålder, patrull/grupp)",
        validators=[Optional(), Length(max=500)],
        render_kw={"rows": 2, "placeholder": "Namn, ålder, patrull/grupp"},
    )
    incident_type = SelectField(
        "Händelsetyp",
        choices=Incident.INCIDENT_TYPES,
        validators=[DataRequired()],
    )
    severity = RadioField(
        "Allvarlighetsgrad",
        choices=Incident.SEVERITY_LEVELS,
        validators=[DataRequired()],
        default="låg",
    )
    description = TextAreaField(
        "Beskrivning",
        validators=[DataRequired(message="Ange beskrivning."), Length(max=5000)],
        render_kw={"rows": 5, "placeholder": "Beskriv vad som hände..."},
    )
    action_taken = TextAreaField(
        "Vidtagna åtgärder",
        validators=[Optional(), Length(max=3000)],
        render_kw={"rows": 3, "placeholder": "Vilka åtgärder vidtogs?"},
    )
    needs_followup = BooleanField("Uppföljning krävs")
    followup_notes = TextAreaField(
        "Uppföljningsanteckning",
        validators=[Optional(), Length(max=2000)],
        render_kw={"rows": 3, "placeholder": "Anteckningar om uppföljning..."},
    )
    status = SelectField(
        "Status",
        choices=Incident.STATUS_OPTIONS,
        validators=[DataRequired()],
    )
    submit = SubmitField("Spara rapport")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        camps = _get_active_camps()
        self.camp_id.choices = [(c.id, c.name) for c in camps]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@incidents_bp.route("/")
@login_required
def list_incidents():
    if current_user.is_admin:
        incidents = Incident.query.order_by(Incident.occurred_at.desc()).all()
    else:
        incidents = (
            Incident.query
            .filter_by(reporter_id=current_user.id)
            .order_by(Incident.occurred_at.desc())
            .all()
        )
    return render_template("incidents/list.html", incidents=incidents)


@incidents_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_incident():
    form = IncidentForm()

    # Pre-fill camp from user's linked camp
    if request.method == "GET":
        form.occurred_at.data = datetime.now()
        if current_user.camp_id:
            form.camp_id.data = current_user.camp_id

    # Get camp for dynamic fields
    selected_camp_id = None
    if request.method == "POST":
        try:
            selected_camp_id = int(request.form.get("camp_id", 0))
        except (ValueError, TypeError):
            selected_camp_id = None
    else:
        # Check for camp_preview GET param (used when changing camp via JS)
        camp_preview = request.args.get("camp_preview", type=int)
        if camp_preview:
            selected_camp_id = camp_preview
            form.camp_id.data = camp_preview
        elif current_user.camp_id:
            selected_camp_id = current_user.camp_id
        elif form.camp_id.choices:
            selected_camp_id = form.camp_id.choices[0][0] if form.camp_id.choices else None

    selected_camp = Camp.query.get(selected_camp_id) if selected_camp_id else None

    if form.validate_on_submit():
        camp = Camp.query.get(form.camp_id.data)
        if not camp:
            flash("Ogiltigt läger.", "danger")
            return render_template("incidents/form.html", form=form, title="Ny rapport", selected_camp=selected_camp)

        # Collect dynamic field data
        extra_data = {}
        if camp.custom_fields:
            for field_def in camp.custom_fields:
                key = field_def.get("key")
                ftype = field_def.get("type")
                if ftype == "checkbox":
                    extra_data[key] = request.form.get(f"extra_{key}") == "on"
                else:
                    val = request.form.get(f"extra_{key}", "").strip()
                    extra_data[key] = val

        incident = Incident(
            camp_id=form.camp_id.data,
            reporter_id=current_user.id,
            occurred_at=form.occurred_at.data,
            involved_person=form.involved_person.data.strip() if form.involved_person.data else None,
            incident_type=form.incident_type.data,
            severity=form.severity.data,
            description=form.description.data.strip(),
            action_taken=form.action_taken.data.strip() if form.action_taken.data else None,
            needs_followup=form.needs_followup.data,
            followup_notes=form.followup_notes.data.strip() if form.followup_notes.data else None,
            status=form.status.data,
            extra_data=extra_data,
        )
        db.session.add(incident)
        db.session.commit()
        flash("Rapport sparad.", "success")
        return redirect(url_for("incidents.view_incident", incident_id=incident.id))

    return render_template(
        "incidents/form.html",
        form=form,
        title="Ny rapport",
        selected_camp=selected_camp,
        incident=None,
    )


@incidents_bp.route("/<int:incident_id>")
@login_required
def view_incident(incident_id):
    incident = Incident.query.get_or_404(incident_id)
    # Access control: users can only view their own reports
    if not current_user.is_admin and incident.reporter_id != current_user.id:
        abort(403)
    return render_template("incidents/view.html", incident=incident)


@incidents_bp.route("/<int:incident_id>/edit", methods=["GET", "POST"])
@login_required
def edit_incident(incident_id):
    incident = Incident.query.get_or_404(incident_id)
    # Access control
    if not current_user.is_admin and incident.reporter_id != current_user.id:
        abort(403)

    form = IncidentForm(obj=incident)

    # Get camp for dynamic fields
    selected_camp_id = None
    if request.method == "POST":
        try:
            selected_camp_id = int(request.form.get("camp_id", 0))
        except (ValueError, TypeError):
            selected_camp_id = incident.camp_id
    else:
        selected_camp_id = incident.camp_id

    selected_camp = Camp.query.get(selected_camp_id) if selected_camp_id else None

    if request.method == "GET":
        form.camp_id.data = incident.camp_id
        # Convert naive datetime to local for form display
        if incident.occurred_at:
            form.occurred_at.data = incident.occurred_at

    if form.validate_on_submit():
        camp = Camp.query.get(form.camp_id.data)
        if not camp:
            flash("Ogiltigt läger.", "danger")
            return render_template(
                "incidents/form.html", form=form, title="Redigera rapport",
                selected_camp=selected_camp, incident=incident
            )

        # Collect dynamic field data
        extra_data = {}
        if camp.custom_fields:
            for field_def in camp.custom_fields:
                key = field_def.get("key")
                ftype = field_def.get("type")
                if ftype == "checkbox":
                    extra_data[key] = request.form.get(f"extra_{key}") == "on"
                else:
                    val = request.form.get(f"extra_{key}", "").strip()
                    extra_data[key] = val

        incident.camp_id = form.camp_id.data
        incident.occurred_at = form.occurred_at.data
        incident.involved_person = form.involved_person.data.strip() if form.involved_person.data else None
        incident.incident_type = form.incident_type.data
        incident.severity = form.severity.data
        incident.description = form.description.data.strip()
        incident.action_taken = form.action_taken.data.strip() if form.action_taken.data else None
        incident.needs_followup = form.needs_followup.data
        incident.followup_notes = form.followup_notes.data.strip() if form.followup_notes.data else None
        incident.status = form.status.data
        incident.extra_data = extra_data
        incident.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        flash("Rapport uppdaterad.", "success")
        return redirect(url_for("incidents.view_incident", incident_id=incident.id))

    return render_template(
        "incidents/form.html",
        form=form,
        title="Redigera rapport",
        selected_camp=selected_camp,
        incident=incident,
    )


@incidents_bp.route("/<int:incident_id>/delete", methods=["POST"])
@login_required
def delete_incident(incident_id):
    incident = Incident.query.get_or_404(incident_id)
    # Only admins or the reporter can delete
    if not current_user.is_admin and incident.reporter_id != current_user.id:
        abort(403)
    db.session.delete(incident)
    db.session.commit()
    flash("Rapport borttagen.", "success")
    return redirect(url_for("incidents.list_incidents"))
