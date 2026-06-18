"""最近使用的 RSSHub 订阅源服务。

约束:
- 每人最多保留 5 条
- 按 last_used_at 降序, 最近用过的在前面
- 同一 (user_id, source_url) 只保留一条, 多次使用会更新 last_used_at + use_count

设计: 直接走 SQL 而不是缓存, 因为读路径也是同一张表 (不取多)。
每次写入 (record_usage) 后顺手 trim, 保持单用户 ≤ 5 条, 不会无限增长。
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.model.models import RecentFeedSource
from app.utils.time import utc_now

# 单用户最多保留的条数, 与设计文档保持一致
MAX_RECENT_PER_USER = 5


def _normalize_source_url(url: str) -> str:
    """chip 复用必须做最小标准化, 否则 'https://x' 和 'https://x/' 会当两条。

    - 前后 trim
    - 末尾 '/' 去掉 (RSSHub 路由通常不带)
    返回 normalized 后的字符串, 不做大小写归一化 (RSSHub 路由大小写敏感)。
    """
    return (url or "").strip().rstrip("/")


def list_recent_sources(
    db: Session, user_id: int, limit: int = MAX_RECENT_PER_USER
) -> List[RecentFeedSource]:
    """返回当前用户最近用过的订阅源, 按 last_used_at 降序。"""
    return (
        db.query(RecentFeedSource)
        .filter(RecentFeedSource.user_id == user_id)
        .order_by(RecentFeedSource.last_used_at.desc())
        .limit(limit)
        .all()
    )


def record_usage(
    db: Session, user_id: int, source_url: str
) -> Optional[RecentFeedSource]:
    """记录一次使用, 并 trim 排名 > 5 的旧记录。

    行为:
    - 同一 (user, url) 已存在: last_used_at = now, use_count += 1
    - 不存在: 新插入一条, last_used_at = now, use_count = 1
    - 写完后: 删掉该 user 排名 6 之后的记录
    - 失败抛异常由调用方 rollback

    返回更新 / 新建的 ORM 对象, 调用方一般不需要, 但保留方便测试断言。
    """
    normalized = _normalize_source_url(source_url)
    if not normalized:
        return None
    now = utc_now()

    existing = (
        db.query(RecentFeedSource)
        .filter(
            RecentFeedSource.user_id == user_id,
            RecentFeedSource.source_url == normalized,
        )
        .first()
    )
    if existing:
        existing.last_used_at = now
        existing.use_count = (existing.use_count or 0) + 1
        existing.updated_at = now
        record = existing
    else:
        record = RecentFeedSource(
            user_id=user_id,
            source_url=normalized,
            use_count=1,
            last_used_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(record)

    # trim: 取该 user 全部记录, 按 last_used_at desc, 排名 > MAX 的删掉
    # 用 id IN (subquery) 一次性删, 避免 race 下误删
    keep_ids = [
        row.id
        for row in (
            db.query(RecentFeedSource.id)
            .filter(RecentFeedSource.user_id == user_id)
            .order_by(RecentFeedSource.last_used_at.desc())
            .limit(MAX_RECENT_PER_USER)
            .all()
        )
    ]
    if keep_ids:
        db.execute(
            delete(RecentFeedSource)
            .where(RecentFeedSource.user_id == user_id)
            .where(~RecentFeedSource.id.in_(keep_ids))
        )
    else:
        # 极端情况: 没保留住任何一条 (例如并发 trim), 不做任何删除
        pass

    return record


def remove_source(db: Session, user_id: int, source_url: str) -> bool:
    """用户主动从 chip 列表里删除一条。返回是否真的删了。"""
    normalized = _normalize_source_url(source_url)
    if not normalized:
        return False
    result = (
        db.query(RecentFeedSource)
        .filter(
            RecentFeedSource.user_id == user_id,
            RecentFeedSource.source_url == normalized,
        )
        .delete(synchronize_session=False)
    )
    return bool(result)
