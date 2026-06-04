"""add vocabulary entries table

Revision ID: 8c2a1d4b7f90
Revises: b7c9f2e9f1d2
Create Date: 2026-06-04 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8c2a1d4b7f90'
down_revision = 'b7c9f2e9f1d2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'vocabulary_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('article_id', sa.Integer(), nullable=True),
        sa.Column('word', sa.String(length=255), nullable=False),
        sa.Column('pronunciation', sa.String(length=255), nullable=True),
        sa.Column('meaning', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='learning'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('mastered_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['article_id'], ['articles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'word', name='uq_vocabulary_entries_user_word'),
    )
    op.create_index(op.f('ix_vocabulary_entries_user_id'), 'vocabulary_entries', ['user_id'], unique=False)
    op.create_index(op.f('ix_vocabulary_entries_article_id'), 'vocabulary_entries', ['article_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_vocabulary_entries_article_id'), table_name='vocabulary_entries')
    op.drop_index(op.f('ix_vocabulary_entries_user_id'), table_name='vocabulary_entries')
    op.drop_table('vocabulary_entries')
