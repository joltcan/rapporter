import io
import csv
import json
import base64
from datetime import date
from functools import wraps

import qrcode
import qrcode.image.svg
from flask import (
    render_template, redirect, url_for, flash, request,
    abort, current_app, make_response, send_file,
)
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import (
    StringField, PasswordField, SelectField, BooleanField,
    SubmitField, DateField, TextAreaField,
)
from wtforms.validators import DataRequired, Length, Optional, ValidationError

from app.admin import admin_bp
from app.models import User, Camp, Incident
from app import db


# ---------------------------------------------------------------------------
# Access control decorator
# ---------------------------------------------------------------------------

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------

class UserForm(FlaskForm):
    username = StringField(
        "Användarnamn",
        validators=[DataRequired(), Length(min=2, max=80)],
        render_kw={"placeholder": "användarnamn"},
    )
    password = PasswordField(
        "Lösenord",
        validators=[Optional(), Length(min=6, message="Minst 6 tecken.")],
        render_kw={"placeholder": "Lämna tomt för att behålla befintligt"},
    )
    role = SelectField(
        "Roll",
        choices=[("user", "Användare"), ("admin", "Administratör")],
        validators=[DataRequired()],
    )
    camp_id = SelectField("Läger", coerce=int, validators=[Optional()])
    submit = SubmitField("Spara")

    def __init__(self, *args, edit_mode=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.edit_mode = edit_mode
        # Populate camp choices
        camps = Camp.query.order_by(Camp.name).all()
        self.camp_id.choices = [(0, "— Inget läger —")] + [(c.id, c.name) for c in camps]

    def validate_password(self, field):
        if not self.edit_mode and not field.data:
            raise ValidationError("Lösenord krävs för nya användare.")


class CampForm(FlaskForm):
    name = StringField(
        "Namn",
        validators=[DataRequired(), Length(min=2, max=200)],
        render_kw={"placeholder": "Lägrets namn"},
    )
    location = StringField(
        "Plats",
        validators=[Optional(), Length(max=300)],
        render_kw={"placeholder": "Adress eller platsnamn"},
    )
    start_date = DateField("Startdatum", validators=[Optional()])
    end_date = DateField("Slutdatum", validators=[Optional()])
    is_active = BooleanField("Aktivt läger")
    submit = SubmitField("Spara")


FIELD_TYPE_CHOICES = [
    ("text", "Fritext"),
    ("dropdown", "Rullgardinsmeny"),
    ("checkbox", "Kryssruta"),
    ("date", "Datum"),
]


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@admin_bp.route("/")
@login_required
@admin_required
def dashboard():
    total_incidents = Incident.query.count()
    open_incidents = Incident.query.filter_by(status="öppen").count()
    total_users = User.query.count()
    total_camps = Camp.query.filter_by(is_active=True).count()
    recent_incidents = (
        Incident.query.order_by(Incident.created_at.desc()).limit(10).all()
    )
    return render_template(
        "admin/dashboard.html",
        total_incidents=total_incidents,
        open_incidents=open_incidents,
        total_users=total_users,
        total_camps=total_camps,
        recent_incidents=recent_incidents,
    )


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------

@admin_bp.route("/users")
@login_required
@admin_required
def users():
    all_users = User.query.order_by(User.username).all()
    return render_template("admin/users.html", users=all_users)


@admin_bp.route("/users/new", methods=["GET", "POST"])
@login_required
@admin_required
def new_user():
    form = UserForm()
    if form.validate_on_submit():
        existing = User.query.filter_by(username=form.username.data.strip()).first()
        if existing:
            flash("Användarnamnet är redan taget.", "danger")
        else:
            user = User(
                username=form.username.data.strip(),
                role=form.role.data,
                camp_id=form.camp_id.data if form.camp_id.data != 0 else None,
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            flash(f"Användare '{user.username}' skapad.", "success")
            return redirect(url_for("admin.users"))
    return render_template("admin/user_form.html", form=form, title="Ny användare", edit_mode=False)


@admin_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    form = UserForm(obj=user, edit_mode=True)

    if request.method == "GET":
        form.camp_id.data = user.camp_id or 0

    if form.validate_on_submit():
        existing = User.query.filter_by(username=form.username.data.strip()).first()
        if existing and existing.id != user.id:
            flash("Användarnamnet är redan taget.", "danger")
        else:
            user.username = form.username.data.strip()
            user.role = form.role.data
            user.camp_id = form.camp_id.data if form.camp_id.data != 0 else None
            if form.password.data:
                user.set_password(form.password.data)
            db.session.commit()
            flash(f"Användare '{user.username}' uppdaterad.", "success")
            return redirect(url_for("admin.users"))
    return render_template(
        "admin/user_form.html", form=form, title="Redigera användare", edit_mode=True, user=user
    )


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("Du kan inte ta bort ditt eget konto.", "danger")
        return redirect(url_for("admin.users"))
    db.session.delete(user)
    db.session.commit()
    flash(f"Användare '{user.username}' borttagen.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/qr")
@login_required
@admin_required
def user_qr(user_id):
    user = User.query.get_or_404(user_id)
    base_url = current_app.config.get("BASE_URL", "https://localhost")
    login_url = f"{base_url}/login?u={user.username}"

    # Generate QR code as PNG base64
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(login_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    return render_template(
        "admin/qr_code.html",
        user=user,
        login_url=login_url,
        img_b64=img_b64,
    )


@admin_bp.route("/users/<int:user_id>/qr/download")
@login_required
@admin_required
def download_qr(user_id):
    user = User.query.get_or_404(user_id)
    base_url = current_app.config.get("BASE_URL", "https://localhost")
    login_url = f"{base_url}/login?u={user.username}"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(login_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return send_file(
        buf,
        mimetype="image/png",
        as_attachment=True,
        download_name=f"qr_{user.username}.png",
    )


# ---------------------------------------------------------------------------
# Camp management
# ---------------------------------------------------------------------------

@admin_bp.route("/camps")
@login_required
@admin_required
def camps():
    all_camps = Camp.query.order_by(Camp.name).all()
    return render_template("admin/camps.html", camps=all_camps)


@admin_bp.route("/camps/new", methods=["GET", "POST"])
@login_required
@admin_required
def new_camp():
    form = CampForm()
    if form.validate_on_submit():
        camp = Camp(
            name=form.name.data.strip(),
            location=form.location.data.strip() if form.location.data else None,
            start_date=form.start_date.data,
            end_date=form.end_date.data,
            is_active=form.is_active.data,
            custom_fields=[],
        )
        db.session.add(camp)
        db.session.commit()
        flash(f"Läger '{camp.name}' skapat.", "success")
        return redirect(url_for("admin.camps"))
    form.is_active.data = True
    return render_template("admin/camp_form.html", form=form, title="Nytt läger", camp=None)


@admin_bp.route("/camps/<int:camp_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_camp(camp_id):
    camp = Camp.query.get_or_404(camp_id)
    form = CampForm(obj=camp)

    if form.validate_on_submit():
        camp.name = form.name.data.strip()
        camp.location = form.location.data.strip() if form.location.data else None
        camp.start_date = form.start_date.data
        camp.end_date = form.end_date.data
        camp.is_active = form.is_active.data
        db.session.commit()
        flash(f"Läger '{camp.name}' uppdaterat.", "success")
        return redirect(url_for("admin.camps"))

    return render_template("admin/camp_form.html", form=form, title="Redigera läger", camp=camp)


@admin_bp.route("/camps/<int:camp_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_camp(camp_id):
    camp = Camp.query.get_or_404(camp_id)
    # Check for linked incidents
    if camp.incidents.count() > 0:
        flash("Kan inte ta bort läger med tillhörande rapporter.", "danger")
        return redirect(url_for("admin.camps"))
    db.session.delete(camp)
    db.session.commit()
    flash(f"Läger '{camp.name}' borttaget.", "success")
    return redirect(url_for("admin.camps"))


# ---------------------------------------------------------------------------
# Custom fields management
# ---------------------------------------------------------------------------

@admin_bp.route("/camps/<int:camp_id>/fields", methods=["GET", "POST"])
@login_required
@admin_required
def camp_fields(camp_id):
    camp = Camp.query.get_or_404(camp_id)

    if request.method == "POST":
        action = request.form.get("action")

        if action == "add_field":
            field_label = request.form.get("field_label", "").strip()
            field_type = request.form.get("field_type", "text")
            field_required = request.form.get("field_required") == "1"
            field_options = request.form.get("field_options", "").strip()

            if not field_label:
                flash("Fältnamn krävs.", "danger")
            elif field_type not in [t[0] for t in FIELD_TYPE_CHOICES]:
                flash("Ogiltigt fälttyp.", "danger")
            else:
                import re
                field_key = re.sub(r"[^a-z0-9_]", "_", field_label.lower())
                field_key = re.sub(r"_+", "_", field_key).strip("_")

                # Ensure unique key
                existing_keys = [f.get("key") for f in (camp.custom_fields or [])]
                base_key = field_key
                counter = 1
                while field_key in existing_keys:
                    field_key = f"{base_key}_{counter}"
                    counter += 1

                new_field = {
                    "key": field_key,
                    "label": field_label,
                    "type": field_type,
                    "required": field_required,
                }
                if field_type == "dropdown" and field_options:
                    new_field["options"] = [o.strip() for o in field_options.split("\n") if o.strip()]

                fields = list(camp.custom_fields or [])
                fields.append(new_field)
                camp.custom_fields = fields
                db.session.commit()
                flash(f"Fält '{field_label}' lagt till.", "success")

        elif action == "delete_field":
            field_key = request.form.get("field_key")
            fields = [f for f in (camp.custom_fields or []) if f.get("key") != field_key]
            camp.custom_fields = fields
            db.session.commit()
            flash("Fält borttaget.", "success")

        return redirect(url_for("admin.camp_fields", camp_id=camp_id))

    return render_template(
        "admin/camp_fields.html",
        camp=camp,
        field_type_choices=FIELD_TYPE_CHOICES,
    )


# ---------------------------------------------------------------------------
# Reports: list, filter, export
# ---------------------------------------------------------------------------

@admin_bp.route("/reports")
@login_required
@admin_required
def reports():
    camps = Camp.query.order_by(Camp.name).all()

    # Filters
    camp_filter = request.args.get("camp_id", type=int)
    status_filter = request.args.get("status", "")
    severity_filter = request.args.get("severity", "")
    type_filter = request.args.get("incident_type", "")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    search = request.args.get("search", "").strip()

    query = Incident.query.order_by(Incident.occurred_at.desc())

    if camp_filter:
        query = query.filter(Incident.camp_id == camp_filter)
    if status_filter:
        query = query.filter(Incident.status == status_filter)
    if severity_filter:
        query = query.filter(Incident.severity == severity_filter)
    if type_filter:
        query = query.filter(Incident.incident_type == type_filter)
    if date_from:
        try:
            from datetime import datetime
            df = datetime.strptime(date_from, "%Y-%m-%d")
            query = query.filter(Incident.occurred_at >= df)
        except ValueError:
            pass
    if date_to:
        try:
            from datetime import datetime, timedelta
            dt = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(Incident.occurred_at < dt)
        except ValueError:
            pass
    if search:
        like = f"%{search}%"
        query = query.filter(
            db.or_(
                Incident.involved_person.ilike(like),
                Incident.description.ilike(like),
                Incident.action_taken.ilike(like),
            )
        )

    incidents = query.all()

    return render_template(
        "admin/reports.html",
        incidents=incidents,
        camps=camps,
        incident_types=Incident.INCIDENT_TYPES,
        severity_levels=Incident.SEVERITY_LEVELS,
        status_options=Incident.STATUS_OPTIONS,
        filters={
            "camp_id": camp_filter,
            "status": status_filter,
            "severity": severity_filter,
            "incident_type": type_filter,
            "date_from": date_from,
            "date_to": date_to,
            "search": search,
        },
    )


@admin_bp.route("/reports/export")
@login_required
@admin_required
def export_reports():
    camp_filter = request.args.get("camp_id", type=int)
    status_filter = request.args.get("status", "")
    severity_filter = request.args.get("severity", "")
    type_filter = request.args.get("incident_type", "")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")

    query = Incident.query.order_by(Incident.occurred_at.desc())

    if camp_filter:
        query = query.filter(Incident.camp_id == camp_filter)
    if status_filter:
        query = query.filter(Incident.status == status_filter)
    if severity_filter:
        query = query.filter(Incident.severity == severity_filter)
    if type_filter:
        query = query.filter(Incident.incident_type == type_filter)
    if date_from:
        try:
            from datetime import datetime
            df = datetime.strptime(date_from, "%Y-%m-%d")
            query = query.filter(Incident.occurred_at >= df)
        except ValueError:
            pass
    if date_to:
        try:
            from datetime import datetime, timedelta
            dt = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(Incident.occurred_at < dt)
        except ValueError:
            pass

    incidents = query.all()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_ALL)

    # Header
    writer.writerow([
        "ID", "Läger", "Rapportör", "Tidpunkt", "Inblandad person",
        "Händelsetyp", "Allvarlighetsgrad", "Beskrivning", "Åtgärd",
        "Uppföljning krävs", "Uppföljningsanteckning", "Status",
        "Skapad", "Uppdaterad",
    ])

    for inc in incidents:
        writer.writerow([
            inc.id,
            inc.camp.name if inc.camp else "",
            inc.reporter.username if inc.reporter else "",
            inc.occurred_at.strftime("%Y-%m-%d %H:%M") if inc.occurred_at else "",
            inc.involved_person or "",
            inc.incident_type,
            inc.severity,
            inc.description,
            inc.action_taken or "",
            "Ja" if inc.needs_followup else "Nej",
            inc.followup_notes or "",
            inc.status,
            inc.created_at.strftime("%Y-%m-%d %H:%M") if inc.created_at else "",
            inc.updated_at.strftime("%Y-%m-%d %H:%M") if inc.updated_at else "",
        ])

    output.seek(0)
    # Add BOM for Excel compatibility with Swedish characters
    bom = "\ufeff"
    response = make_response(bom + output.getvalue())
    response.headers["Content-Disposition"] = "attachment; filename=rapporter.csv"
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    return response
