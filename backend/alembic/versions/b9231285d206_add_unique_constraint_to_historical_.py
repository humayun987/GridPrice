"""add unique constraint to historical_prices

Revision ID: b9231285d206
Revises: 77b0e5ce9cdf
Create Date: 2026-07-08 13:07:32.428142

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b9231285d206'
down_revision: Union[str, None] = '77b0e5ce9cdf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        'historical_prices_market_region_block_uniq',
        'historical_prices',
        ['market', 'region', 'datetime_block']
    )


def downgrade() -> None:
    op.drop_constraint(
        'historical_prices_market_region_block_uniq',
        'historical_prices',
        type_='unique'
    )
