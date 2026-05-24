"""remove raw_mcp_snapshots table

Revision ID: 22ce515eae6f
Revises: 20b689f7ab06
Create Date: 2026-05-24 18:25:51.395688

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '22ce515eae6f'
down_revision: Union[str, None] = '20b689f7ab06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # raw_mcp_snapshots was already dropped manually in pgAdmin
    # This migration just records that decision in version history
    pass


def downgrade() -> None:
    pass