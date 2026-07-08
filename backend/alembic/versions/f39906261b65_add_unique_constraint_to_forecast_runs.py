"""add unique constraint to forecast_runs

Revision ID: f39906261b65
Revises: a35fe4b1e4da
Create Date: 2026-07-08 11:39:59.148408

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f39906261b65'
down_revision: Union[str, None] = 'a35fe4b1e4da'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        'uq_forecast_runs_market_region_date',
        'forecast_runs',
        ['market', 'region', 'forecast_date']
    )


def downgrade() -> None:
    op.drop_constraint(
        'uq_forecast_runs_market_region_date',
        'forecast_runs',
        type_='unique'
    )