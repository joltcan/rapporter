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
from collections import OrderedDict
from datetime import datetime, timezone, timedelta
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
    Ticket, Category, Tag, TicketHistory, User,
    DEFAULT_CATEGORY_SLUG,
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
    # `title` column is kept on the model for future LLM-generated
    # summaries; no form field is exposed to users right now.
    priority = SelectField(
        "Priority",
        coerce=int,
        choices=[(p, f"P{p}") for p in PRIORITIES],
        default=PRIORITY_P3,
        validators=[DataRequired()],
    )
    # Category is the top-level grouping (admin-managed). Choices are
    # populated from the DB at instantiation; the route adds a default
    # so a category is always selected.
    category_id = SelectField(
        "Category",
        coerce=int,
        validators=[DataRequired()],
    )
    # Tags are a free-form comma-separated list. Existing tags are
    # offered via a datalist for autocomplete; new ones are created on
    # the fly via Tag.get_or_create.
    tags = StringField(
        "Tags",
        validators=[Optional(), Length(max=500)],
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
    note = TextAreaField(
        "Internal note",
        validators=[Optional(), Length(max=10000)],
        render_kw={"rows": 3},
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
# Category / tag helpers
# ---------------------------------------------------------------------------

def _category_choices():
    """Build the (id, label) tuple list driving the category dropdown.
    Sorted by sort_order then display_name so admin curation sticks."""
    return [
        (c.id, c.display_name)
        for c in Category.query.order_by(
            Category.sort_order.asc(), Category.display_name.asc()
        ).all()
    ]


def _default_category():
    """The fallback Category every form starts on. Looked up by slug
    so renaming Övrigt's display label in the admin UI doesn't break
    this -- only deleting the slug would, which the admin UI prevents
    for in-use categories."""
    return Category.query.filter_by(name=DEFAULT_CATEGORY_SLUG).first()


def _parse_tags_input(raw):
    """Split a free-form 'a, b, c' string into a normalised list of
    Tag rows. Whitespace and duplicates are collapsed; blank entries
    are dropped. New tag names are created on the fly so editors don't
    have to pre-create them."""
    if not raw:
        return []
    seen = set()
    result = []
    for chunk in raw.split(","):
        norm = Tag.normalise(chunk)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        tag = Tag.get_or_create(chunk)
        if tag is not None:
            result.append(tag)
    return result


def _format_tags(tags):
    """Render the current tags on a ticket back to the comma-separated
    text shown in the form input. Order matches the relationship's
    display_name sort so the field is stable across reads/writes."""
    return ", ".join(t.display_name for t in tags)


def _populate_category_field(form):
    """Attach the dynamic category choices to a TicketForm instance.
    Called from every route that renders the form."""
    form.category_id.choices = _category_choices()


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
    tag_f = request.args.get("tag", type=int)
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
    if tag_f:
        q = q.filter(Ticket.tags.any(Tag.id == tag_f))
    if search:
        like = f"%{search}%"
        q = q.filter(db.or_(
            Ticket.title.ilike(like),
            Ticket.description.ilike(like),
            Ticket.feedback.ilike(like),
        ))

    tickets = q.order_by(Ticket.priority.asc(), Ticket.created_at.desc()).all()
    categories = Category.query.order_by(
        Category.sort_order.asc(), Category.display_name.asc()
    ).all()
    tags = Tag.query.order_by(Tag.display_name.asc()).all()

    return render_template(
        "tickets/list.html",
        tickets=tickets,
        categories=categories,
        tags=tags,
        statuses=STATUSES,
        priorities=PRIORITIES,
        filters={
            "status": status_f,
            "priority": priority_f,
            "category": category_f,
            "tag": tag_f,
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
    _populate_category_field(form)

    if request.method == "GET":
        # Pre-fill timestamp with "now" in local time for the datetime-local input.
        form.created_at.data = datetime.now()
        # Default to Övrigt so the dropdown isn't blank on first paint.
        default = _default_category()
        if default is not None:
            form.category_id.data = default.id

    if form.validate_on_submit():
        cat = Category.query.get(form.category_id.data)
        if cat is None:
            # Belt-and-braces: SelectField validation should have caught
            # this, but if a category was deleted between page load and
            # submit, fall back to the default rather than 500'ing.
            cat = _default_category()
        tag_objs = _parse_tags_input(form.tags.data)

        is_public = bool(form.is_public.data)
        ticket = Ticket(
            description=form.description.data.strip(),
            feedback=(form.feedback.data or "").strip() or None,
            note=(form.note.data or "").strip() or None,
            priority=form.priority.data,
            status=form.status.data,
            is_public=is_public,
            public_token=_new_public_token() if is_public else None,
            category=cat,
            tags=tag_objs,
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
        _log_creation(ticket, current_user)
        db.session.commit()
        flash(_("Ticket saved."), "success")
        return redirect(url_for("tickets.view_ticket", ticket_id=ticket.id))

    all_tags = Tag.query.order_by(Tag.display_name.asc()).all()
    return render_template(
        "tickets/form.html",
        form=form,
        all_tags=all_tags,
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
    _populate_category_field(form)

    if request.method == "GET":
        # `obj=` doesn't populate non-column attrs cleanly: pre-set the
        # category dropdown from the ticket's current FK and the tag
        # input from the comma-joined tag display names.
        form.category_id.data = ticket.category_id
        form.tags.data = _format_tags(ticket.tags)

    if form.validate_on_submit():
        new_cat = Category.query.get(form.category_id.data) or _default_category()
        new_tags = _parse_tags_input(form.tags.data)
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

        new_description = form.description.data.strip()

        # --- Record change log ------------------------------------------
        _log_change(ticket, "description", ticket.description,
                    new_description, current_user)
        _log_change(ticket, "feedback", ticket.feedback,
                    (form.feedback.data or "").strip() or None, current_user)
        _log_change(ticket, "note", ticket.note,
                    (form.note.data or "").strip() or None, current_user)
        _log_change(ticket, "priority", ticket.priority, form.priority.data, current_user)
        _log_change(ticket, "status", ticket.status, new_status, current_user)
        _log_change(ticket, "is_public", ticket.is_public, bool(form.is_public.data), current_user)
        _log_change(ticket, "created_at", ticket.created_at, form.created_at.data, current_user)
        _log_change(ticket, "closed_at", ticket.closed_at, new_closed_at, current_user)
        old_cat_name = ticket.category.display_name if ticket.category else None
        new_cat_name = new_cat.display_name if new_cat else None
        _log_change(ticket, "category", old_cat_name, new_cat_name, current_user)
        # Log the tag set as a single comma-joined string so the diff
        # in the audit log reads naturally instead of one row per tag.
        _log_change(
            ticket,
            "tags",
            _format_tags(ticket.tags) or None,
            ", ".join(t.display_name for t in new_tags) or None,
            current_user,
        )

        # --- Apply changes ----------------------------------------------
        ticket.description = new_description
        ticket.feedback = (form.feedback.data or "").strip() or None
        ticket.note = (form.note.data or "").strip() or None
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
        ticket.tags = new_tags
        ticket.created_at = form.created_at.data
        ticket.closed_at = new_closed_at

        db.session.commit()
        flash(_("Ticket saved."), "success")
        return redirect(url_for("tickets.view_ticket", ticket_id=ticket.id))

    all_tags = Tag.query.order_by(Tag.display_name.asc()).all()
    return render_template(
        "tickets/form.html",
        form=form,
        all_tags=all_tags,
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

# ---------------------------------------------------------------------------
# Morning report -- "what happened in the last 24 hours" view used at the
# daily morning briefing. Defaults to a window from yesterday 08:00 local to
# today 08:00 local (or, before 08:00, day-before-yesterday 08:00 to
# yesterday 08:00). Both ends are user-overridable via query params.
# ---------------------------------------------------------------------------

def _default_window():
    """(start_utc, end_utc) for the most recent 08:00→08:00 window.

    All times in this module's storage are timezone-aware UTC; the morning
    report's "08:00" rotation is interpreted in the server's local timezone
    so the window matches when the camp staff are actually awake.
    """
    now_local = datetime.now().astimezone()
    today_8am = now_local.replace(hour=8, minute=0, second=0, microsecond=0)
    end_local = today_8am if now_local >= today_8am else today_8am - timedelta(days=1)
    start_local = end_local - timedelta(days=1)
    return (
        start_local.astimezone(timezone.utc),
        end_local.astimezone(timezone.utc),
    )


def _parse_local_to_utc(s):
    """Parse '2026-05-04T08:00' as local time, return tz-aware UTC. None on failure."""
    if not s:
        return None
    try:
        naive = datetime.strptime(s, "%Y-%m-%dT%H:%M")
    except ValueError:
        return None
    # Naive datetime + .astimezone() → local-aware; then convert to UTC.
    return naive.astimezone().astimezone(timezone.utc)


def _utc_to_local_input(dt):
    """tz-aware UTC datetime → 'YYYY-MM-DDTHH:MM' local string for datetime-local input."""
    if dt is None:
        return ""
    return dt.astimezone().strftime("%Y-%m-%dT%H:%M")


@tickets_bp.route("/morgonrapport")
@login_required
def morning_report():
    default_start, default_end = _default_window()
    start = _parse_local_to_utc(request.args.get("from")) or default_start
    end = _parse_local_to_utc(request.args.get("to")) or default_end
    if end <= start:
        # Guard against an inverted manual window. Fall back to defaults
        # rather than rendering an empty report.
        start, end = default_start, default_end

    # 1. Tickets created in window.
    new_in_window = (
        Ticket.query
        .filter(Ticket.created_at >= start, Ticket.created_at < end)
        .order_by(Ticket.priority.asc(), Ticket.created_at.asc())
        .all()
    )
    new_ids = {t.id for t in new_in_window}

    # 2. Tickets closed in window. closed_at is set when status enters a
    # terminal state, and re-cleared on reopen, so this gives us the right
    # "actually finished today" set without joining the history table.
    closed_in_window = (
        Ticket.query
        .filter(Ticket.closed_at >= start, Ticket.closed_at < end)
        .order_by(Ticket.closed_at.asc())
        .all()
    )

    # 3. History events in window, grouped by ticket. Skip the synthetic
    # __created__ rows since "new" tickets already get their own section.
    events = (
        TicketHistory.query
        .filter(TicketHistory.changed_at >= start, TicketHistory.changed_at < end)
        .filter(TicketHistory.field != "__created__")
        .order_by(TicketHistory.changed_at.asc())
        .all()
    )
    events_by_ticket = OrderedDict()
    for ev in events:
        # Hide bookkeeping noise from the morning briefing -- updated_at
        # changes constantly and add no signal.
        if ev.field in ("updated_at",):
            continue
        events_by_ticket.setdefault(ev.ticket_id, []).append(ev)

    # Build a parallel ticket map so the template can show ticket meta with
    # each event group without a per-row query.
    ticket_ids = list(events_by_ticket.keys())
    ticket_map = {}
    if ticket_ids:
        for t in Ticket.query.filter(Ticket.id.in_(ticket_ids)).all():
            ticket_map[t.id] = t

    # 4. Currently-open critical/important tickets. Independent of the
    # window: these need attention at the briefing regardless of when they
    # were filed. Excludes anything closed during the window so we don't
    # double-list a ticket that already shows up under "closed".
    open_critical = (
        Ticket.query
        .filter(Ticket.status.in_(OPEN_STATUSES))
        .filter(Ticket.priority.in_((1, 2)))
        .order_by(Ticket.priority.asc(), Ticket.created_at.asc())
        .all()
    )

    return render_template(
        "tickets/morning_report.html",
        start=start,
        end=end,
        from_input=_utc_to_local_input(start),
        to_input=_utc_to_local_input(end),
        new_in_window=new_in_window,
        closed_in_window=closed_in_window,
        events_by_ticket=events_by_ticket,
        ticket_map=ticket_map,
        new_ids=new_ids,
        open_critical=open_critical,
        generated_at=datetime.now(timezone.utc),
    )


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
