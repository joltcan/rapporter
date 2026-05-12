"""Add color column to categories.

Each category can have a hex colour (e.g. #ef5350) that is shown on
ticket badges and the TV board. Default colours are assigned to the
five built-in categories; new categories default to #6c757d.

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

_DEFAULT_COLOR = "#6c757d"

_BUILT_IN_COLORS = {
    "sakerhet": "#ef5350",
    "miljo":    "#66bb6a",
    "halsa":    "#42a5f5",
    "vader":    "#ffca28",
    "ovrigt":   "#78909c",
}


def upgrade():
    op.add_column(
        "categories",
        sa.Column(
            "color",
            sa.String(length=7),
            nullable=False,
            server_default=_DEFAULT_COLOR,
        ),
    )

    for slug, color in _BUILT_IN_COLORS.items():
        op.execute(
            f"UPDATE categories SET color = '{color}' WHERE name = '{slug}'"
        )


def downgrade():
    op.drop_column("categories", "color")
