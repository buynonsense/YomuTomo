"""add ai config fields to user table

Revision ID: 5a1b2c3d4e5f
Revises: 4d060d8cf01e
Create Date: 2025-09-07 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '5a1b2c3d4e5f'
down_revision = '43e2c9be4683'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 添加AI配置字段
    op.add_column('users', sa.Column('openai_api_key', sa.String(500), nullable=True))
    op.add_column('users', sa.Column('openai_base_url', sa.String(500), nullable=True))
    op.add_column('users', sa.Column('openai_model', sa.String(100), nullable=True))


def downgrade() -> None:
    # 删除AI配置字段
    op.drop_column('users', 'openai_api_key')
    op.drop_column('users', 'openai_base_url')
    op.drop_column('users', 'openai_model')
