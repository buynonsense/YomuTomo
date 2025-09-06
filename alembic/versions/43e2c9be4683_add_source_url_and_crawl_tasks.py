"""add_source_url_and_crawl_tasks

Revision ID: 43e2c9be4683
Revises: 4d060d8cf01e
Create Date: 2025-09-07 04:00:20.443055

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '43e2c9be4683'
down_revision = '4d060d8cf01e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 检查并添加source_url字段到articles表
    conn = op.get_bind()
    
    # 检查source_url字段是否存在
    result = conn.execute(sa.text("SELECT column_name FROM information_schema.columns WHERE table_name = 'articles' AND column_name = 'source_url';"))
    source_url_exists = result.fetchone()
    
    if not source_url_exists:
        op.add_column('articles', sa.Column('source_url', sa.String(500), nullable=True))
    
    # 检查crawl_tasks表是否存在
    result = conn.execute(sa.text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'crawl_tasks';"))
    table_exists = result.fetchone()
    
    if not table_exists:
        # 创建crawl_tasks表
        op.create_table('crawl_tasks',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('status', sa.String(50), nullable=False, default='pending'),
            sa.Column('total_articles', sa.Integer(), nullable=False, default=0),
            sa.Column('processed_articles', sa.Integer(), nullable=False, default=0),
            sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, default=sa.func.now()),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        # 创建索引
        op.create_index(op.f('ix_crawl_tasks_user_id'), 'crawl_tasks', ['user_id'], unique=False)


def downgrade() -> None:
    # 删除crawl_tasks表
    op.drop_index(op.f('ix_crawl_tasks_user_id'), table_name='crawl_tasks')
    op.drop_table('crawl_tasks')
    
    # 删除source_url字段
    op.drop_column('articles', 'source_url')


