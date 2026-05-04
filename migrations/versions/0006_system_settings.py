"""Add system_settings key/value table.

A singleton store for runtime-configurable settings: TV display mode,
default morning-report rotation hour, etc. Seeded with the same
defaults the model lists in SETTING_DEFAULTS so a fresh DB starts
with the values the app would otherwise fall back to.

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(length=80), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.execute(
        "INSERT INTO system_settings (key, value, updated_at) VALUES "
        "('tv_show_description', 'true',  NOW()),"
        "('morning_report_hour', '08:00', NOW())"
    )


def downgrade():
    op.drop_table("system_settings")
