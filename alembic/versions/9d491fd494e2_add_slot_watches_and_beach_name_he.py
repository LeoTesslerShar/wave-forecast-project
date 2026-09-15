"""add slot_watches and beach.name_he

Two independent additions bundled into one migration since both landed in the same change:

- `beaches.name_he`: Hebrew display name for the UI (which is Hebrew/RTL only, no i18n
  framework -- docs/DECISIONS.md). Nullable, backfilled by app/seed.py's normal upsert on
  next startup rather than a data migration here -- the seed script is the single source of
  truth for beach data and already runs idempotently on every boot.

- `slot_watches`: a user watching one specific forecast slot for one beach, distinct from
  the standing, recurring `subscriptions` table. See app/models.py::SlotWatch for the full
  state-machine rationale (pending -> alerted -> cancelled, or -> expired). Deliberately a
  new table rather than reusing `subscriptions`/`alerts_sent`: `subscriptions.time_window_
  start/end` are NOT NULL local wall-clock Time columns describing a recurring window, not
  a single absolute instant, and `alerts_sent.subscription_id` is a NOT NULL FK -- extending
  either would weaken an existing invariant rather than model a genuinely different concept.

Revision ID: 9d491fd494e2
Revises: 427208cad892
Create Date: 2026-09-15 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9d491fd494e2"
down_revision: Union[str, None] = "427208cad892"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("beaches", sa.Column("name_he", sa.String(length=128), nullable=True))

    op.create_table(
        "slot_watches",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("beach_id", sa.String(length=64), sa.ForeignKey("beaches.id"), nullable=False),
        sa.Column("valid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("watch_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("alerted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("conditions_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "beach_id", "valid_at", name="uq_slot_watch_slot"),
    )
    op.create_index("ix_slot_watch_user_id", "slot_watches", ["user_id"])
    op.create_index("ix_slot_watch_due", "slot_watches", ["status", "watch_from"])


def downgrade() -> None:
    op.drop_index("ix_slot_watch_due", table_name="slot_watches")
    op.drop_index("ix_slot_watch_user_id", table_name="slot_watches")
    op.drop_table("slot_watches")
    op.drop_column("beaches", "name_he")
