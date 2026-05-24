"""update historical_prices columns for iexrtmprice

Revision ID: 9e0a9f4aafe0
Revises: 22ce515eae6f
Create Date: 2026-05-24 21:26:42.579665

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '9e0a9f4aafe0'
down_revision: Union[str, None] = '22ce515eae6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns
    op.add_column('historical_prices', sa.Column('cleared_buy_mw', sa.Float(), nullable=True))
    op.add_column('historical_prices', sa.Column('cleared_sell_mw', sa.Float(), nullable=True))

    # Remove old columns
    op.drop_column('historical_prices', 'purchase_bid_mw')
    op.drop_column('historical_prices', 'mcv_mw')
    op.drop_column('historical_prices', 'final_scheduled_volume_mw')
    op.drop_column('historical_prices', 'sell_bid_mw')


def downgrade() -> None:
    op.add_column('historical_prices', sa.Column('sell_bid_mw', sa.Float(), nullable=True))
    op.add_column('historical_prices', sa.Column('final_scheduled_volume_mw', sa.Float(), nullable=True))
    op.add_column('historical_prices', sa.Column('mcv_mw', sa.Float(), nullable=True))
    op.add_column('historical_prices', sa.Column('purchase_bid_mw', sa.Float(), nullable=True))
    op.drop_column('historical_prices', 'cleared_sell_mw')
    op.drop_column('historical_prices', 'cleared_buy_mw')