"""Add note column to tickets.

Free-form internal note, only shown to signed-in users. Nullable
because existing rows have no note.

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-20 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tickets",
        sa.Column("note", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("tickets", "note")
