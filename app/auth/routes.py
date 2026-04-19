"""Authentication routes -- login and logout."""

from flask import render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length

from app.auth import auth_bp
from app.models import User
from app import limiter
from app.i18n import gettext as _


class LoginForm(FlaskForm):
    # Labels are plain English; templates localise them on render.
    username = StringField(
        "Username",
        validators=[DataRequired(message="Enter a username."), Length(min=2, max=80)],
        render_kw={"autofocus": True, "autocomplete": "username"},
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(message="Enter a password.")],
        render_kw={"autocomplete": "current-password"},
    )
    remember = BooleanField("Remember me")
    submit = SubmitField("Sign in")


def _post_login_redirect(user):
    """After sign-in, go to the admin dashboard for admins, otherwise to
    the ticket list. Honours the ?next= query arg if it points to a safe
    relative path."""
    next_page = request.args.get("next")
    if next_page and next_page.startswith("/") and not next_page.startswith("//"):
        return redirect(next_page)
    if user.is_admin:
        return redirect(url_for("admin.dashboard"))
    return redirect(url_for("tickets.list_tickets"))


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if current_user.is_authenticated:
        return _post_login_redirect(current_user)

    # QR codes can pre-fill the username via `?u=`. We deliberately don't
    # auto-login -- the user still has to enter their password.
    prefill = request.args.get("u", "")
    form = LoginForm(username=prefill)

    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data.strip()).first()
        if user and user.check_password(form.password.data):
            # Permanent sessions pick up PERMANENT_SESSION_LIFETIME (14 days)
            # so users stay signed in across browser restarts by default.
            session.permanent = True
            login_user(user, remember=form.remember.data)
            return _post_login_redirect(user)
        flash(_("Incorrect username or password."), "danger")

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash(_("You have signed out."), "info")
    return redirect(url_for("auth.login"))
