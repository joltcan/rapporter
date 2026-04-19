"""Admin-only routes: dashboard, user management, category management, QR.

All routes here require the logged-in user to have role=admin."""

import io
import base64
from functools import wraps

import qrcode
from flask import (
    render_template, redirect, url_for, flash, request,
    abort, current_app, send_file,
)
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, Regexp, ValidationError

from app.admin import admin_bp
from app.models import (
    User, Category, Ticket,
    ROLES, ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER,
    STATUSES, STATUS_NEW, STATUS_STARTED, STATUS_CLOSED, STATUS_PAUSED, STATUS_REJECTED,
    PRIORITIES, PRIORITY_P1, PRIORITY_P2, PRIORITY_P3,
)
from app import db
from app.i18n import gettext as _


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


def editor_required(f):
    """Admins + editors. Used for the Overview dashboard, which is a
    read-only aggregate view that is safe to share with editors."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.can_edit:
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------

class UserForm(FlaskForm):
    username = StringField(
        "Username",
        validators=[
            DataRequired(),
            Length(min=2, max=80),
            Regexp(r"^[A-Za-z0-9_.-]+$", message="Only letters, numbers and underscores."),
        ],
    )
    password = PasswordField(
        "Password",
        validators=[Optional(), Length(min=6, message="Password (min 6 characters).")],
    )
    role = SelectField(
        "Role",
        choices=[(ROLE_ADMIN, "Administrator"), (ROLE_EDITOR, "Editor"), (ROLE_VIEWER, "Viewer")],
        default=ROLE_EDITOR,
        validators=[DataRequired()],
    )
    submit = SubmitField("Save")

    def __init__(self, *args, edit_mode=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.edit_mode = edit_mode

    def validate_password(self, field):
        if not self.edit_mode and not field.data:
            raise ValidationError("Password required for new users.")


class CategoryForm(FlaskForm):
    name = StringField(
        "Category name",
        validators=[DataRequired(), Length(min=1, max=80)],
    )
    submit = SubmitField("Save")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@admin_bp.route("/")
@login_required
@editor_required
def dashboard():
    # Count per status (ignore statuses with zero rows gracefully).
    status_counts = {s: Ticket.query.filter_by(status=s).count() for s in STATUSES}
    # Priority counts exclude closed/rejected tickets so the numbers match
    # the "By priority" links, which land on open tickets for that priority.
    open_statuses = (STATUS_NEW, STATUS_STARTED, STATUS_PAUSED)
    priority_counts = {
        p: Ticket.query.filter_by(priority=p).filter(Ticket.status.in_(open_statuses)).count()
        for p in PRIORITIES
    }
    total = Ticket.query.count()
    open_count = (
        status_counts.get(STATUS_NEW, 0)
        + status_counts.get(STATUS_STARTED, 0)
        + status_counts.get(STATUS_PAUSED, 0)
    )
    p1_count = priority_counts.get(PRIORITY_P1, 0)

    # "Queue length" = tickets currently not in a terminal state.
    queue_length = (
        Ticket.query
        .filter(Ticket.status.in_((STATUS_NEW, STATUS_STARTED, STATUS_PAUSED)))
        .count()
    )

    recent = (
        Ticket.query
        .order_by(Ticket.updated_at.desc())
        .limit(10)
        .all()
    )
    latest = (
        Ticket.query
        .order_by(Ticket.created_at.desc())
        .limit(10)
        .all()
    )

    return render_template(
        "admin/dashboard.html",
        total=total,
        open_count=open_count,
        p1_count=p1_count,
        queue_length=queue_length,
        status_counts=status_counts,
        priority_counts=priority_counts,
        # Denominator for the "By priority" progress bars. Priority counts
        # only include open tickets, so scaling to the open subtotal gives
        # a meaningful comparison between priorities.
        priority_total=sum(priority_counts.values()),
        recent=recent,
        latest=latest,
        statuses=STATUSES,
        priorities=PRIORITIES,
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
        uname = form.username.data.strip()
        if User.query.filter_by(username=uname).first():
            flash(_("Username already taken."), "danger")
        else:
            user = User(username=uname, role=form.role.data)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            flash(_("User %(name)s created.", name=user.username), "success")
            return redirect(url_for("admin.users"))
    return render_template(
        "admin/user_form.html",
        form=form,
        title=_("New user"),
        edit_mode=False,
        user=None,
    )


@admin_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    form = UserForm(obj=user, edit_mode=True)

    if form.validate_on_submit():
        uname = form.username.data.strip()
        clash = User.query.filter_by(username=uname).first()
        if clash and clash.id != user.id:
            flash(_("Username already taken."), "danger")
        else:
            user.username = uname
            user.role = form.role.data
            if form.password.data:
                user.set_password(form.password.data)
            db.session.commit()
            flash(_("User %(name)s updated.", name=user.username), "success")
            return redirect(url_for("admin.users"))

    return render_template(
        "admin/user_form.html",
        form=form,
        title=_("Edit user"),
        edit_mode=True,
        user=user,
    )


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash(_("You cannot remove your own account."), "danger")
        return redirect(url_for("admin.users"))
    name = user.username
    db.session.delete(user)
    db.session.commit()
    flash(_("User %(name)s removed.", name=name), "success")
    return redirect(url_for("admin.users"))


# ---------------------------------------------------------------------------
# QR codes for login pre-fill (one per user)
# ---------------------------------------------------------------------------

@admin_bp.route("/users/<int:user_id>/qr")
@login_required
@admin_required
def user_qr(user_id):
    user = User.query.get_or_404(user_id)
    login_url = _login_qr_url(user)
    qr_b64 = _qr_b64(login_url)
    return render_template(
        "admin/qr_code.html",
        user=user,
        login_url=login_url,
        img_b64=qr_b64,
    )


@admin_bp.route("/users/<int:user_id>/qr.png")
@login_required
@admin_required
def download_qr(user_id):
    user = User.query.get_or_404(user_id)
    login_url = _login_qr_url(user)
    buf = io.BytesIO()
    _qr_image(login_url).save(buf, format="PNG")
    buf.seek(0)
    return send_file(
        buf,
        mimetype="image/png",
        as_attachment=True,
        download_name=f"qr_{user.username}.png",
    )


# ---------------------------------------------------------------------------
# Category management
# ---------------------------------------------------------------------------

@admin_bp.route("/categories", methods=["GET", "POST"])
@login_required
@admin_required
def categories():
    form = CategoryForm()
    if form.validate_on_submit():
        raw = form.name.data
        normalised = Category.normalise(raw)
        if not normalised:
            flash(_("Category name is required."), "danger")
        elif Category.query.filter_by(name=normalised).first():
            flash(_("A category with this name already exists."), "danger")
        else:
            Category.get_or_create(raw)
            db.session.commit()
            flash(_("Category added."), "success")
            return redirect(url_for("admin.categories"))

    all_categories = Category.query.order_by(Category.display_name).all()
    return render_template(
        "admin/categories.html",
        categories=all_categories,
        form=form,
    )


@admin_bp.route("/categories/<int:category_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_category(category_id):
    cat = Category.query.get_or_404(category_id)
    # Seed the form with the current display name so the user can tweak
    # casing or wording without retyping the whole thing.
    form = CategoryForm(name=cat.display_name)
    if form.validate_on_submit():
        raw = form.name.data
        normalised = Category.normalise(raw)
        if not normalised:
            flash(_("Category name is required."), "danger")
        else:
            clash = Category.query.filter_by(name=normalised).first()
            if clash and clash.id != cat.id:
                flash(_("A category with this name already exists."), "danger")
            else:
                display = raw.strip()
                display = display[:1].upper() + display[1:] if display else normalised.capitalize()
                cat.name = normalised
                cat.display_name = display
                db.session.commit()
                flash(_("Category renamed."), "success")
                return redirect(url_for("admin.categories"))
    return render_template(
        "admin/category_form.html",
        form=form,
        category=cat,
    )


@admin_bp.route("/categories/<int:category_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_category(category_id):
    cat = Category.query.get_or_404(category_id)
    if cat.tickets.count() > 0:
        flash(_("Cannot remove a category that is in use."), "danger")
    else:
        db.session.delete(cat)
        db.session.commit()
        flash(_("Category removed."), "success")
    return redirect(url_for("admin.categories"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _login_qr_url(user):
    base = current_app.config.get("BASE_URL", "http://localhost").rstrip("/")
    return f"{base}/login?u={user.username}"


def _qr_image(url):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white")


def _qr_b64(url):
    buf = io.BytesIO()
    _qr_image(url).save(buf, format="PNG")
    buf.seek(0)
    return base64.b64encode(buf.getvalue()).decode("ascii")
