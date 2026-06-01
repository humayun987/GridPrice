"""add rain column to raw_weather_forecasts

Revision ID: a35fe4b1e4da
Revises: 9e0a9f4aafe0
Create Date: 2026-06-01 15:43:43.605311

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a35fe4b1e4da'
down_revision: Union[str, None] = '9e0a9f4aafe0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column('raw_weather_forecasts', sa.Column('rain', sa.Float(), nullable=True))

def downgrade() -> None:
    op.drop_column('raw_weather_forecasts', 'rain')