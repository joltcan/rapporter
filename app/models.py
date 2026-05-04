"""Database models for the Scout ticket system.

Three user roles:
  - admin:  full access, manages users, categories, settings
  - editor: creates and edits tickets
  - viewer: read-only access to tickets

Ticket statuses: ny, paborjad, avslutad, pausad, avvisad
Priorities: 1 (P1 akut), 2 (P2 viktig), 3 (P3 lag)
"""

from datetime import datetime, timezone
from flask_login import UserMixin
from app import db
from app.wordlist import random_word


def _new_public_token():
    """A single Swedish word used as a share secret. Kept short so it can
    be read aloud or copied from a printed QR paper if needed; combined
    with per-ticket uniqueness and rate limiting on the public endpoint
    this is strong enough for the low-sensitivity public view."""
    return random_word()


# Role constants -- stored in the DB exactly as listed.
ROLE_ADMIN = "admin"
ROLE_EDITOR = "editor"
ROLE_VIEWER = "viewer"
ROLES = (ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER)

# Ticket status constants -- stored in the DB as ASCII slugs so that SQL
# queries are portable and locale-independent. The user-facing labels are
# resolved at render time via i18n.
STATUS_NEW = "ny"
STATUS_STARTED = "paborjad"
STATUS_CLOSED = "avslutad"
STATUS_PAUSED = "pausad"
STATUS_REJECTED = "avvisad"
STATUSES = (STATUS_NEW, STATUS_STARTED, STATUS_CLOSED, STATUS_PAUSED, STATUS_REJECTED)

# Statuses that represent "finished" work. When a ticket transitions into
# one of these, closed_at is auto-filled.
TERMINAL_STATUSES = (STATUS_CLOSED, STATUS_REJECTED)

# Priorities: 1 = most urgent.
PRIORITY_P1 = 1
PRIORITY_P2 = 2
PRIORITY_P3 = 3
PRIORITIES = (PRIORITY_P1, PRIORITY_P2, PRIORITY_P3)


def _now_utc():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default=ROLE_VIEWER)
    created_at = db.Column(db.DateTime(timezone=True), default=_now_utc)

    tickets = db.relationship("Ticket", back_populates="reporter", lazy="dynamic")

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"

    def check_password(self, password):
        import bcrypt
        return bcrypt.checkpw(password.encode("utf-8"), self.password_hash.encode("utf-8"))

    def set_password(self, password):
        import bcrypt
        self.password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @property
    def is_admin(self):
        return self.role == ROLE_ADMIN

    @property
    def can_edit(self):
        # Admins and editors can create/modify tickets; viewers cannot.
        return self.role in (ROLE_ADMIN, ROLE_EDITOR)


# Default top-level category every ticket falls back to when nothing
# more specific is picked. Admins may rename it but the slug is fixed
# so the seed migration and the form-default lookup always agree.
DEFAULT_CATEGORY_SLUG = "ovrigt"


class Category(db.Model):
    """Top-level grouping of tickets (Säkerhet, Miljö, Hälsa, Väder,
    Övrigt by default). Admin-managed: created and removed from the
    /admin/categories page. Each ticket belongs to exactly one Category;
    free-form labels live on the separate Tag model.
    """
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    display_name = db.Column(db.String(80), nullable=False)
    # Manual ordering -- categories render in this order in dropdowns,
    # admin lists, and the morning report. Defaults to 0 so newly added
    # categories sort to the top until the admin slots them in.
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), default=_now_utc)

    tickets = db.relationship("Ticket", back_populates="category", lazy="dynamic")
    tags = db.relationship(
        "Tag", secondary="tag_categories", back_populates="categories"
    )

    def __repr__(self):
        return f"<Category {self.name}>"

    @staticmethod
    def normalise(raw):
        """Strip surrounding whitespace and lowercase. Collapses internal
        whitespace so 'Säkerhet  ' and 'säkerhet' match."""
        if raw is None:
            return ""
        return " ".join(raw.strip().lower().split())


class Tag(db.Model):
    """Free-form ticket label, used mainly for after-the-fact analysis.
    A ticket can carry many tags; a tag may belong to zero or more
    top-level Categories.

    Like the previous Category model: `name` is the normalised slug
    used for de-dup, `display_name` keeps the casing the user typed.
    """
    __tablename__ = "tags"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    display_name = db.Column(db.String(80), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=_now_utc)

    tickets = db.relationship(
        "Ticket", secondary="ticket_tags", back_populates="tags", lazy="dynamic"
    )
    categories = db.relationship(
        "Category", secondary="tag_categories", back_populates="tags"
    )

    def __repr__(self):
        return f"<Tag {self.name}>"

    @staticmethod
    def normalise(raw):
        if raw is None:
            return ""
        return " ".join(raw.strip().lower().split())

    @classmethod
    def get_or_create(cls, raw_name):
        """Look up by normalised name, or create a new Tag. Returns None
        for empty input. Preserves the caller's preferred casing for
        display, with the first letter capitalised."""
        name = cls.normalise(raw_name)
        if not name:
            return None
        tag = cls.query.filter_by(name=name).first()
        if tag is None:
            display = raw_name.strip()
            display = display[:1].upper() + display[1:] if display else name.capitalize()
            tag = cls(name=name, display_name=display)
            db.session.add(tag)
            db.session.flush()
        return tag


# Association tables for the two many-to-many relationships introduced
# alongside the category/tag split. Defined as Tables (not models) since
# they carry no extra columns; cascade deletes handle cleanup when the
# parent rows are removed.
ticket_tags = db.Table(
    "ticket_tags",
    db.Column(
        "ticket_id",
        db.Integer,
        db.ForeignKey("tickets.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column(
        "tag_id",
        db.Integer,
        db.ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

tag_categories = db.Table(
    "tag_categories",
    db.Column(
        "tag_id",
        db.Integer,
        db.ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column(
        "category_id",
        db.Integer,
        db.ForeignKey("categories.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Ticket(db.Model):
    __tablename__ = "tickets"

    id = db.Column(db.Integer, primary_key=True)

    # Timestamps. `created_at` is the user-editable "Skapad" value that may
    # be backdated for tickets entered after the fact. `db_created_at`
    # records the immutable row-insertion moment.
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_now_utc)
    db_created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_now_utc)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_now_utc,
        onupdate=_now_utc,
    )
    closed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Core content
    title = db.Column(db.String(200), nullable=True)
    description = db.Column(db.Text, nullable=False)
    feedback = db.Column(db.String(500), nullable=True)
    # Free-form internal note. Only shown to signed-in users; never
    # exposed on the public share view.
    note = db.Column(db.Text, nullable=True)

    # Classification
    priority = db.Column(db.Integer, nullable=False, default=PRIORITY_P3)
    # Top-level category. Required at the DB level: every ticket must
    # land somewhere, with "Övrigt" as the default fallback. Routes set
    # the FK to the seeded default when the user doesn't pick one.
    category_id = db.Column(
        db.Integer, db.ForeignKey("categories.id"), nullable=False
    )
    status = db.Column(db.String(20), nullable=False, default=STATUS_NEW)
    is_public = db.Column(db.Boolean, nullable=False, default=False)
    # Auto-generated share secret. Only populated while is_public is True;
    # cleared when the ticket is made private so re-sharing yields a fresh
    # token and old links stop working.
    public_token = db.Column(db.String(32), nullable=True, index=True)

    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    category = db.relationship("Category", back_populates="tickets")
    tags = db.relationship(
        "Tag", secondary="ticket_tags", back_populates="tickets",
        order_by="Tag.display_name",
    )
    reporter = db.relationship("User", back_populates="tickets")
    history = db.relationship(
        "TicketHistory",
        back_populates="ticket",
        order_by="TicketHistory.changed_at.asc()",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Ticket #{self.id} {self.status}>"


class UserAuditLog(db.Model):
    """Audit log for user-account events. One row per field change
    (or a '__created__' row on account creation). Passwords are logged
    as a field change with empty values -- we never store the plaintext."""
    __tablename__ = "user_audit_log"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    changed_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_now_utc)
    field = db.Column(db.String(40), nullable=False)
    old_value = db.Column(db.Text, nullable=True)
    new_value = db.Column(db.Text, nullable=True)

    user = db.relationship("User", foreign_keys=[user_id])
    actor = db.relationship("User", foreign_keys=[actor_id])

    def __repr__(self):
        return f"<UserAuditLog user={self.user_id} {self.field}>"


class SystemSetting(db.Model):
    """Singleton key/value store for admin-configurable runtime settings.
    Each row is one setting. Values are stored as text; helpers below
    coerce to bool / time so callers don't sprinkle parsing everywhere.

    Used for things that may change at any time and shouldn't require a
    container restart (TV display mode, morning-report rotation hour,
    etc.). Not for per-user preferences -- those belong on User.
    """
    __tablename__ = "system_settings"

    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.Text, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_now_utc,
        onupdate=_now_utc,
    )

    def __repr__(self):
        return f"<SystemSetting {self.key}={self.value!r}>"

    @classmethod
    def get(cls, key, default=None):
        row = cls.query.get(key)
        return row.value if row else default

    @classmethod
    def get_bool(cls, key, default=False):
        v = cls.get(key)
        if v is None:
            return default
        return v.strip().lower() in ("true", "1", "yes", "on")

    @classmethod
    def set(cls, key, value):
        """Upsert. Caller is responsible for committing."""
        if isinstance(value, bool):
            value = "true" if value else "false"
        row = cls.query.get(key)
        if row is None:
            row = cls(key=key, value=str(value))
            db.session.add(row)
        else:
            row.value = str(value)
        return row


# Setting key constants -- defined here so model + routes + migrations
# all reference the same strings. Defaults live alongside.
SETTING_TV_SHOW_DESCRIPTION = "tv_show_description"
SETTING_MORNING_REPORT_HOUR = "morning_report_hour"

SETTING_DEFAULTS = {
    SETTING_TV_SHOW_DESCRIPTION: "true",
    SETTING_MORNING_REPORT_HOUR: "08:00",
}


class TicketHistory(db.Model):
    """Audit log for ticket changes. A single row represents one field
    changing on one ticket at one moment. Batched edits produce several
    rows sharing a timestamp."""
    __tablename__ = "ticket_history"

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    changed_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_now_utc)
    field = db.Column(db.String(40), nullable=False)
    old_value = db.Column(db.Text, nullable=True)
    new_value = db.Column(db.Text, nullable=True)

    ticket = db.relationship("Ticket", back_populates="history")
    user = db.relationship("User")

    def __repr__(self):
        return f"<TicketHistory {self.ticket_id}.{self.field}>"
