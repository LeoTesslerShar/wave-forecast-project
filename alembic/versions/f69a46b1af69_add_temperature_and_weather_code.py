"""add temperature_c and weather_code to forecasts

Air temperature and WMO weather code, from the same api.open-meteo.com/v1/forecast request
already used for wind (app/clients/open_meteo_forecast.py) -- verified live, both fields
are genuinely returned alongside wind_speed_10m for the same coordinates/hours. Nullable
and backfill-free, same discipline as the earlier wave_peak_period migration: existing rows
were never fetched with these fields and a fabricated value would misrepresent a
measurement that was never made. Rows stay NULL until the next ingestion run refreshes them.

Revision ID: f69a46b1af69
Revises: 9d491fd494e2
Create Date: 2026-09-16 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f69a46b1af69"
down_revision: Union[str, None] = "9d491fd494e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("forecasts", sa.Column("temperature_c", sa.Float(), nullable=True))
    op.add_column("forecasts", sa.Column("weather_code", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("forecasts", "weather_code")
    op.drop_column("forecasts", "temperature_c")
