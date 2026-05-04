"""Split ticket categorisation into top-level Category + free-form Tag.

Pre-migration the `categories` table held free-form labels created by
editors; it is now repurposed:

  * old `categories` rows become rows in a new `tags` table (free-form
    labels, many-per-ticket via ticket_tags),
  * a fresh `categories` table holds five admin-managed top-level
    groups (Säkerhet, Miljö, Hälsa, Väder, Övrigt) with sort_order,
  * each ticket keeps a single `category_id` (now FK to the new
    `categories` table, default Övrigt) and gains 0..n tags via
    `ticket_tags`,
  * tags can be associated with multiple categories via tag_categories
    (initially empty -- admin curates from /admin/tags).

Existing tickets carry their old single category through as a tag and
land under "Övrigt"; admins can re-categorise after the fact.

Downgrade is lossy: only the first tag of each ticket is preserved as
the category, and tag-category links are dropped.

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Drop the existing FK from tickets.category_id so we can rename
    # the table it points at without dragging the FK along.
    op.drop_constraint("tickets_category_id_fkey", "tickets", type_="foreignkey")

    # 2. Rename the old categories table -> tags (rows preserved, IDs
    # preserved, so the upcoming ticket_tags backfill can use the same
    # category_id values directly).
    op.rename_table("categories", "tags")

    # 3. usage_count was a pre-computed counter on the old categories
    # model. The new design queries on demand, so drop the column.
    op.drop_column("tags", "usage_count")

    # 4. ticket_tags: many-to-many between tickets and tags.
    op.create_table(
        "ticket_tags",
        sa.Column(
            "ticket_id",
            sa.Integer(),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            sa.Integer(),
            sa.ForeignKey("tags.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    # 5. Backfill: every ticket that had a category gets that category
    # carried forward as its first (and only) tag.
    op.execute(
        "INSERT INTO ticket_tags (ticket_id, tag_id) "
        "SELECT id, category_id FROM tickets WHERE category_id IS NOT NULL"
    )

    # 6. Brand-new categories table for the top-level concept.
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=80), nullable=False, unique=True),
        sa.Column("display_name", sa.String(length=80), nullable=False),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # 7. Seed the five default categories. Slugs are ASCII so URLs and
    # lookups don't depend on the locale of the database connection.
    op.execute(
        "INSERT INTO categories (name, display_name, sort_order, created_at) VALUES "
        "('sakerhet', 'Säkerhet', 1, NOW()),"
        "('miljo',    'Miljö',    2, NOW()),"
        "('halsa',    'Hälsa',    3, NOW()),"
        "('vader',    'Väder',    4, NOW()),"
        "('ovrigt',   'Övrigt',   5, NOW())"
    )

    # 8. Repoint every ticket at "Övrigt" -- the previous values pointed
    # at the renamed table and have already been preserved as tags.
    # The categories table is freshly populated so we don't need the FK
    # active yet; CREATE FOREIGN KEY runs after the data is consistent.
    op.execute(
        "UPDATE tickets "
        "SET category_id = (SELECT id FROM categories WHERE name = 'ovrigt')"
    )

    # 9. Re-attach the FK with the new target, then tighten the column
    # to NOT NULL now that every row has a value.
    op.create_foreign_key(
        "tickets_category_id_fkey",
        "tickets",
        "categories",
        ["category_id"],
        ["id"],
    )
    op.alter_column("tickets", "category_id", nullable=False)

    # 10. tag_categories: many-to-many between tags and categories.
    op.create_table(
        "tag_categories",
        sa.Column(
            "tag_id",
            sa.Integer(),
            sa.ForeignKey("tags.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("categories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade():
    # Symmetric reverse, but lossy: only the first tag per ticket
    # survives as the category, tag-category links are dropped, and
    # any ticket that had no tags ends up with category_id = NULL.
    op.drop_table("tag_categories")

    # Detach the FK and relax the NOT NULL so we can shuffle values.
    op.drop_constraint("tickets_category_id_fkey", "tickets", type_="foreignkey")
    op.alter_column("tickets", "category_id", nullable=True)
    op.execute("UPDATE tickets SET category_id = NULL")

    op.drop_table("categories")

    # Restore "first tag becomes the category" semantics. Picking the
    # smallest tag_id is arbitrary but deterministic.
    op.execute(
        "UPDATE tickets t SET category_id = ("
        "  SELECT tt.tag_id FROM ticket_tags tt "
        "  WHERE tt.ticket_id = t.id "
        "  ORDER BY tt.tag_id ASC LIMIT 1"
        ")"
    )

    op.drop_table("ticket_tags")

    # Restore the old usage_count column on what's about to become
    # `categories` again, then recompute it from tickets.
    op.add_column(
        "tags",
        sa.Column(
            "usage_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.execute(
        "UPDATE tags t SET usage_count = ("
        "  SELECT COUNT(*) FROM tickets WHERE category_id = t.id"
        ")"
    )

    op.rename_table("tags", "categories")
    op.create_foreign_key(
        "tickets_category_id_fkey",
        "tickets",
        "categories",
        ["category_id"],
        ["id"],
    )
