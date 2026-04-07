from datetime import datetime, timezone
from flask_login import UserMixin
from app import db


class Camp(db.Model):
    __tablename__ = "camps"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    location = db.Column(db.String(300), nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    custom_fields = db.Column(db.JSON, nullable=False, default=list)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    users = db.relationship("User", back_populates="camp", lazy="dynamic")
    incidents = db.relationship("Incident", back_populates="camp", lazy="dynamic")

    def __repr__(self):
        return f"<Camp {self.name}>"

    def get_custom_fields(self):
        """Return custom_fields as list, ensuring correct structure."""
        if self.custom_fields is None:
            return []
        return self.custom_fields


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="user")  # 'admin' or 'user'
    camp_id = db.Column(db.Integer, db.ForeignKey("camps.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    camp = db.relationship("Camp", back_populates="users")
    incidents = db.relationship("Incident", back_populates="reporter", lazy="dynamic")

    def __repr__(self):
        return f"<User {self.username}>"

    def check_password(self, password):
        import bcrypt
        return bcrypt.checkpw(password.encode("utf-8"), self.password_hash.encode("utf-8"))

    def set_password(self, password):
        import bcrypt
        self.password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @property
    def is_admin(self):
        return self.role == "admin"


class Incident(db.Model):
    __tablename__ = "incidents"

    id = db.Column(db.Integer, primary_key=True)
    camp_id = db.Column(db.Integer, db.ForeignKey("camps.id"), nullable=False)
    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    occurred_at = db.Column(db.DateTime(timezone=True), nullable=False)
    involved_person = db.Column(db.Text, nullable=True)
    incident_type = db.Column(db.String(50), nullable=False)
    severity = db.Column(db.String(20), nullable=False)
    description = db.Column(db.Text, nullable=False)
    action_taken = db.Column(db.Text, nullable=True)
    needs_followup = db.Column(db.Boolean, default=False, nullable=False)
    followup_notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="öppen")
    extra_data = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    camp = db.relationship("Camp", back_populates="incidents")
    reporter = db.relationship("User", back_populates="incidents")

    def __repr__(self):
        return f"<Incident {self.id} - {self.incident_type}>"

    INCIDENT_TYPES = [
        ("olycka", "Olycka"),
        ("sjukdom", "Sjukdom"),
        ("konflikt", "Konflikt"),
        ("materialbrist", "Materialbrist"),
        ("säkerhet", "Säkerhet"),
        ("övrigt", "Övrigt"),
    ]

    SEVERITY_LEVELS = [
        ("låg", "Låg"),
        ("medium", "Medium"),
        ("hög", "Hög"),
    ]

    STATUS_OPTIONS = [
        ("öppen", "Öppen"),
        ("pågående", "Pågående"),
        ("stängd", "Stängd"),
    ]
