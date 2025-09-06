"""add user level

Revision ID: 4d060d8cf01e
Revises: d3861d2070f6
Create Date: 2025-09-07 03:35:23.654620

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '4d060d8cf01e'
down_revision = 'd3861d2070f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 先添加level字段，允许NULL
    op.add_column('users', sa.Column('level', sa.Integer(), nullable=True))
    # 为现有记录设置默认值
    op.execute("UPDATE users SET level = 1 WHERE level IS NULL")
    # 然后设置NOT NULL约束
    op.alter_column('users', 'level', nullable=False)


def downgrade() -> None:
    # 删除level字段
    op.drop_column('users', 'level')


