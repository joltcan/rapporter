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


class Category(db.Model):
    """Ticket category. The `name` column stores a normalised (lowercase,
    trimmed) key so duplicates are impossible. `display_name` preserves the
    casing the user originally typed so we can render it as they entered it
    (the UI itself always capitalises the first letter for consistency).
    """
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    display_name = db.Column(db.String(80), nullable=False)
    usage_count = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), default=_now_utc)

    tickets = db.relationship("Ticket", back_populates="category", lazy="dynamic")

    def __repr__(self):
        return f"<Category {self.name}>"

    @staticmethod
    def normalise(raw):
        """Strip surrounding whitespace and lowercase. Collapses internal
        whitespace so that 'Matlagning  ' and 'matlagning' match."""
        if raw is None:
            return ""
        return " ".join(raw.strip().lower().split())

    @classmethod
    def get_or_create(cls, raw_name):
        """Look up (by normalised name) or create a Category. Returns None
        for empty input."""
        name = cls.normalise(raw_name)
        if not name:
            return None
        cat = cls.query.filter_by(name=name).first()
        if cat is None:
            # Preserve the caller's preferred casing for display, with the
            # first letter capitalised so the UI looks tidy.
            display = raw_name.strip()
            display = display[:1].upper() + display[1:] if display else name.capitalize()
            cat = cls(name=name, display_name=display, usage_count=0)
            db.session.add(cat)
            db.session.flush()
        return cat


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

    # Classification
    priority = db.Column(db.Integer, nullable=False, default=PRIORITY_P3)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)
    status = db.Column(db.String(20), nullable=False, default=STATUS_NEW)
    is_public = db.Column(db.Boolean, nullable=False, default=False)

    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    category = db.relationship("Category", back_populates="tickets")
    reporter = db.relationship("User", back_populates="tickets")
    history = db.relationship(
        "TicketHistory",
        back_populates="ticket",
        order_by="TicketHistory.changed_at.asc()",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Ticket #{self.id} {self.status}>"


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
