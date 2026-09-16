"""add email to subscriptions and slot_watches

An optional second delivery channel alongside Web Push (app/alerting/email.py, Gmail
SMTP/app-password style). Opt-in per subscription/watch, not a global account setting --
this project has no real user accounts, just the opaque user_id already on both tables.
Nullable, no backfill: existing rows genuinely have no email on file, and null already
means "push only" in the application logic, so there is nothing to fill in.

Revision ID: dd5e182beb64
Revises: f69a46b1af69
Create Date: 2026-09-17 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "dd5e182beb64"
down_revision: Union[str, None] = "f69a46b1af69"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("email", sa.String(length=256), nullable=True))
    op.add_column("slot_watches", sa.Column("email", sa.String(length=256), nullable=True))


def downgrade() -> None:
    op.drop_column("slot_watches", "email")
    op.drop_column("subscriptions", "email")
