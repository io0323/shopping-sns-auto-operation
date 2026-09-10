"""add generation_source to contents

Revision ID: 39a9a96f3228
Revises: 8f04441daac6
Create Date: 2026-09-09 18:40:30.558208

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '39a9a96f3228'
down_revision: Union[str, Sequence[str], None] = '8f04441daac6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 既存行は Generator Agent 経由の生成なので 'api' で埋める。
    op.add_column(
        "contents",
        sa.Column(
            "generation_source",
            sa.String(length=16),
            nullable=False,
            server_default="api",
        ),
    )


def downgrade() -> None:
    op.drop_column("contents", "generation_source")
