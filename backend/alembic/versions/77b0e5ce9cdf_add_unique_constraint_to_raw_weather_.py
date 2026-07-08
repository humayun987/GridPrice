"""add unique constraint to raw_weather_forecasts

Revision ID: 77b0e5ce9cdf
Revises: f39906261b65
Create Date: 2026-07-08 12:57:47.444186

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '77b0e5ce9cdf'
down_revision: Union[str, None] = 'f39906261b65'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        'uq_raw_weather_region_datetime_hour',
        'raw_weather_forecasts',
        ['region', 'datetime_hour']
    )


def downgrade() -> None:
    op.drop_constraint(
        'uq_raw_weather_region_datetime_hour',
        'raw_weather_forecasts',
        type_='unique'
    )