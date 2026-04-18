"""Add public_token to tickets.

A short share secret attached to public tickets. The column is nullable
because the vast majority of tickets are private. Indexed because the
public endpoint looks it up on every request.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-18 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tickets",
        sa.Column("public_token", sa.String(length=32), nullable=True),
    )
    op.create_index(
        "ix_tickets_public_token",
        "tickets",
        ["public_token"],
    )


def downgrade():
    op.drop_index("ix_tickets_public_token", table_name="tickets")
    op.drop_column("tickets", "public_token")
