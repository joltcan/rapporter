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
from wtforms.widgets import PasswordInput

from app.admin import admin_bp
from app.models import (
    User, Category, Tag, Ticket, UserAuditLog,
    DEFAULT_CATEGORY_SLUG,
    ROLES, ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER,
    STATUSES, STATUS_NEW, STATUS_STARTED, STATUS_CLOSED, STATUS_PAUSED, STATUS_REJECTED,
    PRIORITIES, PRIORITY_P1, PRIORITY_P2, PRIORITY_P3,
)
from app import db
from app.i18n import gettext as _
from app.wordlist import random_word


def _log_user_event(user, field, old, new, actor):
    """Append an audit-log row for a user-account event.

    Caller commits. `field='__created__'` marks account creation;
    `field='password'` is recorded with empty old/new so plaintext
    is never persisted.
    """
    entry = UserAuditLog(
        user_id=user.id,
        actor_id=actor.id if actor and actor.is_authenticated else None,
        field=field,
        old_value=None if old is None else str(old),
        new_value=None if new is None else str(new),
    )
    db.session.add(entry)


def _suggest_password():
    """Generate a human-friendly starter password: <word><NN><word>.

    Two Swedish nouns wrapping a two-digit number -- readable,
    typeable, and well above the 6-character minimum. The admin can
    still overwrite it with anything they prefer before saving.

    Words containing åäö are skipped so the generated password is
    easy to type on any keyboard layout (mobile, foreign guests, etc.).
    bcrypt handles UTF-8 fine; this is purely a distribution-UX choice.
    """
    import secrets

    def _ascii_word():
        while True:
            w = random_word()
            if w.isascii():
                return w

    n = secrets.randbelow(100)
    return f"{_ascii_word()}{n:02d}{_ascii_word()}"


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
    # `hide_value=False` lets us pre-fill a generated starter password
    # on the new-user form. Edit-form starts empty (field data is None),
    # so this doesn't leak any existing hash.
    password = PasswordField(
        "Password",
        validators=[Optional(), Length(min=6, message="Password (min 6 characters).")],
        widget=PasswordInput(hide_value=False),
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
    sort_order = StringField(
        "Sort order",
        # Stored as integer in the model; coerced in the route. Optional
        # so admins can leave it blank and accept the default of 0.
        validators=[Optional(), Length(max=6)],
    )
    submit = SubmitField("Save")


class TagForm(FlaskForm):
    name = StringField(
        "Tag name",
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
    if request.method == "GET":
        # Pre-fill with a memorable starter password so the admin has
        # something to copy out of the box; they can still change it.
        form.password.data = _suggest_password()
    if form.validate_on_submit():
        uname = form.username.data.strip()
        if User.query.filter_by(username=uname).first():
            flash(_("Username already taken."), "danger")
        else:
            user = User(username=uname, role=form.role.data)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.flush()
            _log_user_event(user, "__created__", None, None, current_user)
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
            if uname != user.username:
                _log_user_event(user, "username", user.username, uname, current_user)
                user.username = uname
            if form.role.data != user.role:
                _log_user_event(user, "role", user.role, form.role.data, current_user)
                user.role = form.role.data
            if form.password.data:
                user.set_password(form.password.data)
                _log_user_event(user, "password", None, None, current_user)
            db.session.commit()
            flash(_("User %(name)s updated.", name=user.username), "success")
            return redirect(url_for("admin.users"))

    audit_log = (
        UserAuditLog.query
        .filter_by(user_id=user.id)
        .order_by(UserAuditLog.changed_at.desc())
        .all()
    )
    return render_template(
        "admin/user_form.html",
        form=form,
        title=_("Edit user"),
        edit_mode=True,
        user=user,
        audit_log=audit_log,
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
# Category management -- top-level groups (Säkerhet, Miljö, Hälsa, Väder,
# Övrigt by default). Admin-managed: editors and viewers can read but not
# modify the list.
# ---------------------------------------------------------------------------

def _parse_sort_order(raw):
    """Coerce the form's sort_order text input to an int. Empty string
    becomes 0 (the model default); non-numeric input also falls back to
    0 so a typo doesn't block the save."""
    if raw is None or raw == "":
        return 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


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
            display = raw.strip()
            display = display[:1].upper() + display[1:] if display else normalised.capitalize()
            cat = Category(
                name=normalised,
                display_name=display,
                sort_order=_parse_sort_order(form.sort_order.data),
            )
            db.session.add(cat)
            db.session.commit()
            flash(_("Category added."), "success")
            return redirect(url_for("admin.categories"))

    all_categories = Category.query.order_by(
        Category.sort_order.asc(), Category.display_name.asc()
    ).all()
    # Pre-compute usage counts so the template can disable delete on any
    # in-use category without N+1 queries.
    usage = {
        c.id: c.tickets.count() for c in all_categories
    }
    return render_template(
        "admin/categories.html",
        categories=all_categories,
        usage=usage,
        form=form,
    )


@admin_bp.route("/categories/<int:category_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_category(category_id):
    cat = Category.query.get_or_404(category_id)
    form = CategoryForm(name=cat.display_name, sort_order=str(cat.sort_order))
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
                cat.sort_order = _parse_sort_order(form.sort_order.data)
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
    # Don't let the default category be removed -- new tickets fall back
    # to it, so its absence would break the create form.
    if cat.name == DEFAULT_CATEGORY_SLUG:
        flash(_("The default category cannot be removed."), "danger")
    elif cat.tickets.count() > 0:
        flash(_("Cannot remove a category that is in use."), "danger")
    else:
        db.session.delete(cat)
        db.session.commit()
        flash(_("Category removed."), "success")
    return redirect(url_for("admin.categories"))


# ---------------------------------------------------------------------------
# Tag management -- free-form labels editors create on the fly when
# filing tickets. Admins can rename, delete unused, and curate which
# top-level categories each tag belongs to (m2m, optional).
# ---------------------------------------------------------------------------

@admin_bp.route("/tags", methods=["GET", "POST"])
@login_required
@admin_required
def tags():
    form = TagForm()
    if form.validate_on_submit():
        raw = form.name.data
        normalised = Tag.normalise(raw)
        if not normalised:
            flash(_("Tag name is required."), "danger")
        elif Tag.query.filter_by(name=normalised).first():
            flash(_("A tag with this name already exists."), "danger")
        else:
            Tag.get_or_create(raw)
            db.session.commit()
            flash(_("Tag added."), "success")
            return redirect(url_for("admin.tags"))

    all_tags = Tag.query.order_by(Tag.display_name.asc()).all()
    usage = {t.id: t.tickets.count() for t in all_tags}
    return render_template(
        "admin/tags.html",
        tags=all_tags,
        usage=usage,
        form=form,
    )


@admin_bp.route("/tags/<int:tag_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_tag(tag_id):
    tag = Tag.query.get_or_404(tag_id)
    form = TagForm(name=tag.display_name)
    all_categories = Category.query.order_by(
        Category.sort_order.asc(), Category.display_name.asc()
    ).all()
    if request.method == "POST" and form.validate_on_submit():
        raw = form.name.data
        normalised = Tag.normalise(raw)
        if not normalised:
            flash(_("Tag name is required."), "danger")
        else:
            clash = Tag.query.filter_by(name=normalised).first()
            if clash and clash.id != tag.id:
                flash(_("A tag with this name already exists."), "danger")
            else:
                display = raw.strip()
                display = display[:1].upper() + display[1:] if display else normalised.capitalize()
                tag.name = normalised
                tag.display_name = display
                # Update tag-category membership from checkbox state.
                # Each checkbox is named cat_<id>; only the IDs that
                # come back through request.form are kept.
                selected_ids = {
                    int(v)
                    for k, v in request.form.items()
                    if k.startswith("cat_") and v.isdigit()
                }
                tag.categories = [c for c in all_categories if c.id in selected_ids]
                db.session.commit()
                flash(_("Tag renamed."), "success")
                return redirect(url_for("admin.tags"))
    return render_template(
        "admin/tag_form.html",
        form=form,
        tag=tag,
        all_categories=all_categories,
    )


@admin_bp.route("/tags/<int:tag_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_tag(tag_id):
    tag = Tag.query.get_or_404(tag_id)
    if tag.tickets.count() > 0:
        flash(_("Cannot remove a tag that is in use."), "danger")
    else:
        db.session.delete(tag)
        db.session.commit()
        flash(_("Tag removed."), "success")
    return redirect(url_for("admin.tags"))


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
