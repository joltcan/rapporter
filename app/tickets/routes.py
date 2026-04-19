"""Ticket routes: list, create, view, edit, delete, public view, QR code.

Access rules:
  * admin  -- unrestricted
  * editor -- may create new tickets and edit any ticket
  * viewer -- read-only on every ticket
  * anonymous -- may only see tickets that have `is_public=True`, via
                 the dedicated `/tickets/p/<id>` public route
"""

import io
import base64
import hmac
from datetime import datetime, timezone
from functools import wraps

import qrcode
from flask import (
    render_template, redirect, url_for, flash, request,
    abort, current_app, send_file, make_response,
)
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import (
    StringField, SelectField, TextAreaField, BooleanField,
    SubmitField, DateTimeLocalField, HiddenField, IntegerField,
)
from wtforms.validators import DataRequired, Optional, Length, NumberRange

from app.tickets import tickets_bp
from app.models import (
    Ticket, Category, TicketHistory, User,
    STATUSES, STATUS_NEW, STATUS_STARTED, STATUS_PAUSED, STATUS_CLOSED, STATUS_REJECTED,
    TERMINAL_STATUSES,
    PRIORITIES, PRIORITY_P3,
    _new_public_token,
)

OPEN_STATUSES = (STATUS_NEW, STATUS_STARTED, STATUS_PAUSED)

# One-click forward transitions available on the ticket view. Paused and
# rejected are off the happy path and remain manual-via-edit.
NEXT_STATUS = {
    STATUS_NEW: STATUS_STARTED,
    STATUS_STARTED: STATUS_CLOSED,
}
from app import db, limiter
from app.i18n import gettext as _, status_label, priority_label


# ---------------------------------------------------------------------------
# Permission helpers
# ---------------------------------------------------------------------------

def editor_required(f):
    """Admins + editors only -- blocks viewers and anonymous users."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.can_edit:
            abort(403)
        return f(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------

class TicketForm(FlaskForm):
    # Created timestamp is user-editable so admins can backdate tickets
    # that were collected on paper.
    created_at = DateTimeLocalField(
        "Created",
        format="%Y-%m-%dT%H:%M",
        validators=[DataRequired()],
    )
    # Closed timestamp can be set directly for retroactive entries. It is
    # also auto-filled when the status transitions into a terminal state.
    closed_at = DateTimeLocalField(
        "Closed",
        format="%Y-%m-%dT%H:%M",
        validators=[Optional()],
    )
    title = StringField(
        "Title",
        validators=[Optional(), Length(max=200)],
    )
    priority = SelectField(
        "Priority",
        coerce=int,
        choices=[(p, f"P{p}") for p in PRIORITIES],
        default=PRIORITY_P3,
        validators=[DataRequired()],
    )
    # Category is submitted as a free-text field so users can either pick
    # an existing one (via datalist autocomplete) or type a new one. The
    # server normalises and looks it up in the Category table.
    category = StringField(
        "Category",
        validators=[Optional(), Length(max=80)],
    )
    description = TextAreaField(
        "Description",
        validators=[DataRequired(message="Description is required."), Length(max=10000)],
        render_kw={"rows": 6},
    )
    feedback = StringField(
        "Feedback",
        validators=[Optional(), Length(max=500)],
    )
    status = SelectField(
        "Status",
        choices=[(s, s) for s in STATUSES],
        default=STATUS_NEW,
        validators=[DataRequired()],
    )
    is_public = BooleanField("Public")
    submit = SubmitField("Save ticket")


# ---------------------------------------------------------------------------
# History helpers
# ---------------------------------------------------------------------------

def _log_change(ticket, field, old, new, user=None):
    """Append a single change row. Converts values to strings; None stays
    None so the template can show `(empty)`."""
    def norm(v):
        if v is None:
            return None
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)

    old_s, new_s = norm(old), norm(new)
    if old_s == new_s:
        return
    db.session.add(TicketHistory(
        ticket=ticket,
        user=user,
        field=field,
        old_value=old_s,
        new_value=new_s,
    ))


def _log_creation(ticket, user):
    db.session.add(TicketHistory(
        ticket=ticket,
        user=user,
        field="__created__",
        old_value=None,
        new_value=None,
    ))


# ---------------------------------------------------------------------------
# List + filter
# ---------------------------------------------------------------------------

@tickets_bp.route("/")
@login_required
def list_tickets():
    # Default to open tickets when the user hasn't touched the status
    # filter. The list-filter form always submits status= (possibly empty
    # for "Any status"), so an explicit "show everything" pick still works.
    if "status" in request.args:
        status_f = request.args.get("status", "")
    else:
        status_f = "open"
    priority_f = request.args.get("priority", "")
    category_f = request.args.get("category", type=int)
    search = request.args.get("search", "").strip()

    q = Ticket.query
    # "open" is a pseudo-value covering the three non-terminal statuses,
    # used by the Overview KPI cards. Concrete status slugs still work.
    if status_f == "open":
        q = q.filter(Ticket.status.in_(OPEN_STATUSES))
    elif status_f and status_f in STATUSES:
        q = q.filter(Ticket.status == status_f)
    if priority_f:
        try:
            pri = int(priority_f)
            if pri in PRIORITIES:
                q = q.filter(Ticket.priority == pri)
        except (TypeError, ValueError):
            pass
    if category_f:
        q = q.filter(Ticket.category_id == category_f)
    if search:
        like = f"%{search}%"
        q = q.filter(db.or_(
            Ticket.title.ilike(like),
            Ticket.description.ilike(like),
            Ticket.feedback.ilike(like),
        ))

    tickets = q.order_by(Ticket.priority.asc(), Ticket.created_at.desc()).all()
    categories = Category.query.order_by(Category.display_name).all()

    return render_template(
        "tickets/list.html",
        tickets=tickets,
        categories=categories,
        statuses=STATUSES,
        priorities=PRIORITIES,
        filters={
            "status": status_f,
            "priority": priority_f,
            "category": category_f,
            "search": search,
        },
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

@tickets_bp.route("/new", methods=["GET", "POST"])
@login_required
@editor_required
def new_ticket():
    form = TicketForm()

    if request.method == "GET":
        # Pre-fill timestamp with "now" in local time for the datetime-local input.
        form.created_at.data = datetime.now()

    if form.validate_on_submit():
        cat = Category.get_or_create(form.category.data) if form.category.data else None

        is_public = bool(form.is_public.data)
        ticket = Ticket(
            title=(form.title.data or "").strip() or None,
            description=form.description.data.strip(),
            feedback=(form.feedback.data or "").strip() or None,
            priority=form.priority.data,
            status=form.status.data,
            is_public=is_public,
            public_token=_new_public_token() if is_public else None,
            category=cat,
            reporter=current_user,
            created_at=form.created_at.data,
            closed_at=form.closed_at.data,
        )
        # If the user set a terminal status but no closed_at, auto-fill it.
        if ticket.status in TERMINAL_STATUSES and ticket.closed_at is None:
            ticket.closed_at = datetime.now(timezone.utc)
        # Conversely, if the user set closed_at but status is still open,
        # we leave both as entered -- admins may want to backfill closed-at
        # on a ticket that is still Paused etc. for reporting purposes.

        db.session.add(ticket)
        db.session.flush()
        if cat is not None:
            cat.usage_count = (cat.usage_count or 0) + 1
        _log_creation(ticket, current_user)
        db.session.commit()
        flash(_("Ticket saved."), "success")
        return redirect(url_for("tickets.view_ticket", ticket_id=ticket.id))

    categories = Category.query.order_by(Category.display_name).all()
    return render_template(
        "tickets/form.html",
        form=form,
        categories=categories,
        ticket=None,
        title=_("New ticket"),
    )


# ---------------------------------------------------------------------------
# View (authenticated -- shows everything)
# ---------------------------------------------------------------------------

@tickets_bp.route("/<int:ticket_id>")
@login_required
def view_ticket(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    # Heal legacy public tickets that were published before the token
    # column existed -- make sure a public ticket always has a token so
    # the QR code encodes a working URL.
    if ticket.is_public and not ticket.public_token:
        ticket.public_token = _new_public_token()
        db.session.commit()
    share_url = _public_url(ticket) if ticket.is_public else _internal_url(ticket)
    qr_b64 = _qr_png_b64(share_url)
    next_status = NEXT_STATUS.get(ticket.status)
    # Button label is English; view.html pipes it through _() for localisation.
    # Resolve uses a distinct colour from Start so the two actions aren't
    # both green -- which reads as "done" twice over.
    next_status_meta = {
        STATUS_STARTED: ("Start", "bi-play-fill", "btn-success"),
        STATUS_CLOSED: ("Resolve", "bi-check2-circle", "btn-dark"),
    }
    next_label, next_icon, next_btn = next_status_meta.get(next_status, (None, None, None))
    return render_template(
        "tickets/view.html",
        ticket=ticket,
        qr_b64=qr_b64,
        share_url=share_url,
        history=ticket.history,
        next_status=next_status,
        next_status_label=next_label,
        next_status_icon=next_icon,
        next_status_btn=next_btn,
    )


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------

@tickets_bp.route("/<int:ticket_id>/edit", methods=["GET", "POST"])
@login_required
@editor_required
def edit_ticket(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    form = TicketForm(obj=ticket)

    if request.method == "GET":
        # `obj=` populates form fields from ticket attrs, but the category
        # field on the ticket is a Category object; swap in the display name
        # so the text input renders correctly.
        form.category.data = ticket.category.display_name if ticket.category else ""

    if form.validate_on_submit():
        new_cat = Category.get_or_create(form.category.data) if form.category.data else None
        new_status = form.status.data
        new_closed_at = form.closed_at.data
        # Auto-fill closed_at when transitioning into a terminal status.
        if (
            ticket.status not in TERMINAL_STATUSES
            and new_status in TERMINAL_STATUSES
            and new_closed_at is None
        ):
            new_closed_at = datetime.now(timezone.utc)
        # Reopening: clear closed_at when moving from a terminal status
        # back to an open one. A non-terminal ticket with a closed
        # timestamp is inconsistent.
        if (
            ticket.status in TERMINAL_STATUSES
            and new_status not in TERMINAL_STATUSES
        ):
            new_closed_at = None

        new_title = (form.title.data or "").strip() or None
        new_description = form.description.data.strip()

        # --- Record change log ------------------------------------------
        _log_change(ticket, "title", ticket.title, new_title, current_user)
        _log_change(ticket, "description", ticket.description,
                    new_description, current_user)
        _log_change(ticket, "feedback", ticket.feedback,
                    (form.feedback.data or "").strip() or None, current_user)
        _log_change(ticket, "priority", ticket.priority, form.priority.data, current_user)
        _log_change(ticket, "status", ticket.status, new_status, current_user)
        _log_change(ticket, "is_public", ticket.is_public, bool(form.is_public.data), current_user)
        _log_change(ticket, "created_at", ticket.created_at, form.created_at.data, current_user)
        _log_change(ticket, "closed_at", ticket.closed_at, new_closed_at, current_user)
        old_cat_name = ticket.category.display_name if ticket.category else None
        new_cat_name = new_cat.display_name if new_cat else None
        _log_change(ticket, "category", old_cat_name, new_cat_name, current_user)

        # --- Update category usage_count ---------------------------------
        if ticket.category_id != (new_cat.id if new_cat else None):
            if ticket.category is not None:
                ticket.category.usage_count = max(0, (ticket.category.usage_count or 1) - 1)
            if new_cat is not None:
                new_cat.usage_count = (new_cat.usage_count or 0) + 1

        # --- Apply changes ----------------------------------------------
        ticket.title = new_title
        ticket.description = new_description
        ticket.feedback = (form.feedback.data or "").strip() or None
        ticket.priority = form.priority.data
        ticket.status = new_status
        now_public = bool(form.is_public.data)
        ticket.is_public = now_public
        # Token lifecycle: ensure a token exists while the ticket is
        # public; clear it when it goes private. Covers the off->on
        # transition and the legacy case where a public ticket has no
        # token yet (pre-migration data).
        if now_public and not ticket.public_token:
            ticket.public_token = _new_public_token()
        elif not now_public:
            ticket.public_token = None
        ticket.category = new_cat
        ticket.created_at = form.created_at.data
        ticket.closed_at = new_closed_at

        db.session.commit()
        flash(_("Ticket saved."), "success")
        return redirect(url_for("tickets.view_ticket", ticket_id=ticket.id))

    categories = Category.query.order_by(Category.display_name).all()
    return render_template(
        "tickets/form.html",
        form=form,
        categories=categories,
        ticket=ticket,
        title=_("Edit"),
    )


# ---------------------------------------------------------------------------
# Advance -- one-click forward transition: ny → påbörjad → avslutad.
# ---------------------------------------------------------------------------

@tickets_bp.route("/<int:ticket_id>/advance", methods=["POST"])
@login_required
@editor_required
def advance_ticket(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    next_status = NEXT_STATUS.get(ticket.status)
    if next_status is None:
        flash(_("You are not allowed to do that."), "danger")
        return redirect(url_for("tickets.view_ticket", ticket_id=ticket.id))

    old_status = ticket.status
    old_closed_at = ticket.closed_at
    ticket.status = next_status
    if next_status in TERMINAL_STATUSES and ticket.closed_at is None:
        ticket.closed_at = datetime.now(timezone.utc)

    _log_change(ticket, "status", old_status, ticket.status, current_user)
    _log_change(ticket, "closed_at", old_closed_at, ticket.closed_at, current_user)
    db.session.commit()
    flash(_("Ticket saved."), "success")
    return redirect(url_for("tickets.view_ticket", ticket_id=ticket.id))


# ---------------------------------------------------------------------------
# Delete (admin only -- viewers and editors cannot destroy data)
# ---------------------------------------------------------------------------

@tickets_bp.route("/<int:ticket_id>/delete", methods=["POST"])
@login_required
def delete_ticket(ticket_id):
    if not current_user.is_admin:
        abort(403)
    ticket = Ticket.query.get_or_404(ticket_id)
    # Decrement the category usage counter before the cascade cleans up
    # the ticket rows.
    if ticket.category is not None:
        ticket.category.usage_count = max(0, (ticket.category.usage_count or 1) - 1)
    db.session.delete(ticket)
    db.session.commit()
    flash(_("Ticket removed."), "success")
    return redirect(url_for("tickets.list_tickets"))


# ---------------------------------------------------------------------------
# Public view (anonymous -- shows only non-sensitive fields)
# ---------------------------------------------------------------------------

@tickets_bp.route("/p/<int:ticket_id>/<token>")
@limiter.limit("30 per minute")
def public_ticket(ticket_id, token):
    ticket = Ticket.query.get_or_404(ticket_id)
    # Reject if not public, no token on file, or token mismatch. Use a
    # constant-time compare so timing doesn't leak the token.
    if not ticket.is_public or not ticket.public_token:
        abort(404)
    # Compare as bytes -- hmac.compare_digest rejects str with non-ASCII
    # characters (the Swedish wordlist contains å/ä/ö).
    if not hmac.compare_digest(
        ticket.public_token.encode("utf-8"), token.encode("utf-8")
    ):
        abort(404)
    return render_template("tickets/public.html", ticket=ticket)


# ---------------------------------------------------------------------------
# QR code (PNG download for the ticket's share URL)
# ---------------------------------------------------------------------------

@tickets_bp.route("/<int:ticket_id>/qr.png")
@login_required
def ticket_qr_png(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    if ticket.is_public and not ticket.public_token:
        ticket.public_token = _new_public_token()
        db.session.commit()
    url = _public_url(ticket) if ticket.is_public else _internal_url(ticket)
    buf = io.BytesIO()
    _qr_png(url).save(buf, format="PNG")
    buf.seek(0)
    return send_file(
        buf,
        mimetype="image/png",
        as_attachment=True,
        download_name=f"ticket_{ticket.id}_qr.png",
    )


# ---------------------------------------------------------------------------
# TV dashboard -- publicly visible board showing statuses in columns.
# Shows only ticket id, status, created/closed times, priority and title
# (if a title is set). No description, no category.
# ---------------------------------------------------------------------------

@tickets_bp.route("/tv")
def tv_dashboard():
    # Anyone on the camp LAN can pull up the board -- no login required.
    # The columns exclude Paused and Rejected to keep the board tight.
    visible = ("ny", "paborjad", "avslutad")
    columns = {}
    for status in visible:
        columns[status] = (
            Ticket.query
            .filter(Ticket.status == status)
            .order_by(Ticket.priority.asc(), Ticket.created_at.desc())
            .limit(25)
            .all()
        )
    return render_template(
        "tickets/tv.html",
        columns=columns,
        visible_statuses=visible,
    )


# ---------------------------------------------------------------------------
# URL + QR helpers
# ---------------------------------------------------------------------------

def _base_url():
    return current_app.config.get("BASE_URL", "http://localhost").rstrip("/")


def _public_url(ticket):
    if not ticket.public_token:
        return None
    return f"{_base_url()}/tickets/p/{ticket.id}/{ticket.public_token}"


def _internal_url(ticket):
    return f"{_base_url()}/tickets/{ticket.id}"


def _qr_png(data):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white")


def _qr_png_b64(data):
    buf = io.BytesIO()
    _qr_png(data).save(buf, format="PNG")
    buf.seek(0)
    return base64.b64encode(buf.getvalue()).decode("ascii")
