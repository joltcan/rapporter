from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length

from app.auth import auth_bp
from app.models import User
from app import limiter


class LoginForm(FlaskForm):
    username = StringField(
        "Användarnamn",
        validators=[DataRequired(message="Ange användarnamn."), Length(min=2, max=80)],
        render_kw={"placeholder": "Användarnamn", "autofocus": True},
    )
    password = PasswordField(
        "Lösenord",
        validators=[DataRequired(message="Ange lösenord.")],
        render_kw={"placeholder": "Lösenord"},
    )
    remember = BooleanField("Kom ihåg mig")
    submit = SubmitField("Logga in")


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("incidents.list_incidents"))

    # Pre-fill username from query param (used by QR codes)
    prefill_username = request.args.get("u", "")
    form = LoginForm(username=prefill_username)

    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data.strip()).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get("next")
            # Security: only allow relative redirects
            if next_page and next_page.startswith("/") and not next_page.startswith("//"):
                return redirect(next_page)
            if user.is_admin:
                return redirect(url_for("admin.dashboard"))
            return redirect(url_for("incidents.list_incidents"))
        else:
            flash("Felaktigt användarnamn eller lösenord.", "danger")

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Du har loggat ut.", "info")
    return redirect(url_for("auth.login"))
