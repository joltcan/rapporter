"""Add user_audit_log table.

Records who created a user and who changed username, role, or
password on an existing account. Passwords are logged as field
changes with empty old/new values so plaintext is never persisted.

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-21 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("field", sa.String(length=40), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_user_audit_log_user_id",
        "user_audit_log",
        ["user_id"],
    )


def downgrade():
    op.drop_index("ix_user_audit_log_user_id", table_name="user_audit_log")
    op.drop_table("user_audit_log")
