"""add recent feed sources table

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
Create Date: 2026-06-16 12:00:00.000000

新增 recent_feed_sources 表: 每个用户最多 5 条最近用过的 RSSHub 订阅源,
供 /news_center 页面快速选择 chip 复用。

设计要点:
- 唯一约束 (user_id, source_url), 同一用户对同一订阅源只有一条记录
- 写多读少, 索引 user_id + last_used_at 让"取最近 5 条"是 O(5)
- user 删除时 CASCADE 清掉
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7b8c9d0e1f2'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'recent_feed_sources',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('source_url', sa.String(length=500), nullable=False),
        sa.Column('use_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('last_used_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'source_url', name='uq_recent_feed_sources_user_url'),
    )
    op.create_index(op.f('ix_recent_feed_sources_user_id'), 'recent_feed_sources', ['user_id'], unique=False)
    op.create_index(op.f('ix_recent_feed_sources_last_used_at'), 'recent_feed_sources', ['last_used_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_recent_feed_sources_last_used_at'), table_name='recent_feed_sources')
    op.drop_index(op.f('ix_recent_feed_sources_user_id'), table_name='recent_feed_sources')
    op.drop_table('recent_feed_sources')
