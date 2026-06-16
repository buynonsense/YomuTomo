"""clean placeholder vocabulary entries (meaning / pronunciation pending)

Revision ID: f1a2b3c4d5e6
Revises: 8c2a1d4b7f90
Create Date: 2026-06-16 12:00:00.000000

历史脏数据：旧版 AI 抽取生词时, 释义和读音拿不到就回退到正则启发式
并写入占位串 "释义待补充" / "读音待补充"。用户已经明确:

    1) 不需要读音
    2) 释义要么是 AI 真给的中文, 要么就不要占位文字

所以这个迁移把这两个字段里的占位值清成 NULL, 让模板 (vocabulary.html /
reading.html) 通过 `clean_meaning` filter 渲染成 "—"。

不删整行: 单词本身可能仍然有用, 只是释义脏了; 用户后续重新生成文章或
手动补充都可以。
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e6'
down_revision = '8c2a1d4b7f90'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 占位符清单从 app.utils.placeholder_texts 拿, 跟
    # services.py::_parse_vocab_json / templates.py::_clean_meaning 同步。
    from app.utils.placeholder_texts import (
        PLACEHOLDER_MEANINGS,
        PLACEHOLDER_PRONUNCIATIONS,
    )
    from sqlalchemy.orm import Session
    from app.model.models import Article
    import json
    import logging

    logger = logging.getLogger("alembic.runtime.migration")
    _PLACEHOLDER_MEANINGS = tuple(PLACEHOLDER_MEANINGS)
    _PLACEHOLDER_PRONUNCIATIONS = tuple(PLACEHOLDER_PRONUNCIATIONS)

    bind = op.get_bind()
    vocab = sa.table(
        'vocabulary_entries',
        sa.column('meaning', sa.String),
        sa.column('pronunciation', sa.String),
    )

    # 1. 清空脏 meaning (占位串 -> NULL)
    bind.execute(
        vocab.update()
        .where(vocab.c.meaning.in_(_PLACEHOLDER_MEANINGS))
        .values(meaning=None)
    )

    # 2. 清空脏 pronunciation (含 "读音待补充" 和空串 -> NULL)
    bind.execute(
        vocab.update()
        .where(vocab.c.pronunciation.in_(_PLACEHOLDER_PRONUNCIATIONS))
        .values(pronunciation=None)
    )

    # 3. 同时也清理 article.vocab_json 里嵌的占位词条。
    #    vocab_json 是 TEXT, 形如:
    #        [{"word": "X", "pronunciation": "读音待补充", "meaning": "释义待补充"}]
    #    用 Python 拉下来 - 过滤 - 写回, 单次迁移里跑, 简单粗暴。
    session = Session(bind=bind)
    try:
        rows = session.query(Article.id, Article.vocab_json).all()
        touched = 0
        for article_id, vocab_json in rows:
            if not vocab_json:
                continue
            try:
                parsed = json.loads(vocab_json)
            except Exception:
                continue
            if not isinstance(parsed, list):
                continue

            cleaned = []
            changed = False
            for entry in parsed:
                if not isinstance(entry, dict):
                    continue
                # pronunciation 不再需要, 直接丢弃
                if 'pronunciation' in entry:
                    del entry['pronunciation']
                    changed = True
                m = (entry.get('meaning') or '').strip() if entry.get('meaning') else ''
                if m in _PLACEHOLDER_MEANINGS:
                    entry['meaning'] = None
                    changed = True
                w = (entry.get('word') or '').strip() if entry.get('word') else ''
                if not w:
                    # 单词为空 / 没意义, 整条丢
                    changed = True
                    continue
                if not entry.get('meaning'):
                    # 没释义的旧词条也丢掉, 不让 "释义：—" 长期挂在那里
                    changed = True
                    continue
                cleaned.append(entry)

            if changed:
                session.execute(
                    sa.update(Article)
                    .where(Article.id == article_id)
                    .values(vocab_json=json.dumps(cleaned, ensure_ascii=False))
                )
                touched += 1
        if touched:
            session.commit()
        logger.info("cleaned vocab placeholders in %d articles", touched)
    finally:
        session.close()


def downgrade() -> None:
    # 不可逆: 占位串已经被清掉, 旧数据丢失
    pass
