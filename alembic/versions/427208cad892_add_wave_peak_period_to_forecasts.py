"""add wave_peak_period to forecasts

Peak period (Tp) fetched from a second marine model -- see
app/clients/open_meteo_marine.py PEAK_PERIOD_MODEL and docs/DECISIONS.md. Nullable and
backfill-free on purpose: existing rows genuinely do not have a peak period (it was never
fetched), and writing a converted value from the mean period would fabricate measurements
that were never made. Rows stay NULL until the next ingestion run refreshes them, and
quality scoring falls back to the mean period meanwhile, saying so in its confidence field.

Revision ID: 427208cad892
Revises: 6e6eeb20b8df
Create Date: 2026-09-14 16:33:53.213502

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "427208cad892"
down_revision: Union[str, None] = "6e6eeb20b8df"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("forecasts", sa.Column("wave_peak_period", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("forecasts", "wave_peak_period")
