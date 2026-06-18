from __future__ import annotations

from typing import Iterable

import pykakasi
from sqlalchemy.orm import Session

from app.model.models import Article, VocabularyEntry
from app.utils.time import datetime_to_isoformat, utc_now

_kks = pykakasi.kakasi()


def _reading_to_romaji(reading: str) -> str:
    """把假名读音机械转成罗马字 (hepburn)。失败返回 ''。"""
    if not reading:
        return ""
    try:
        parts = _kks.convert(reading)
    except Exception:
        return ""
    return "".join((p.get("hepburn") or "") for p in parts).strip()


def _normalize_word(word: str) -> str:
    return (word or "").strip()


def seed_vocabulary_entries(
    db: Session,
    user_id: int,
    article_id: int | None,
    vocab_items: list[dict],
) -> int:
    """把 AI 提取的词汇写入持久化生词表，已存在的词不重复创建。"""
    created_count = 0

    for item in vocab_items:
        word = _normalize_word(item.get("word", ""))
        if not word:
            continue

        existing = (
            db.query(VocabularyEntry)
            .filter(VocabularyEntry.user_id == user_id, VocabularyEntry.word == word)
            .first()
        )
        if existing:
            continue

        entry = VocabularyEntry(
            user_id=user_id,
            article_id=article_id,
            word=word,
            pronunciation=_normalize_word(item.get("pronunciation", "")) or None,
            meaning=_normalize_word(item.get("meaning", "")) or None,
            status="learning",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.add(entry)
        created_count += 1

    if created_count:
        db.flush()

    return created_count


def toggle_vocabulary_status(
    db: Session,
    user_id: int,
    word: str,
    pronunciation: str | None = None,
    meaning: str | None = None,
    mastered: bool = True,
    article_id: int | None = None,
) -> VocabularyEntry:
    """创建或更新单个词条的掌握状态。"""
    normalized_word = _normalize_word(word)
    if not normalized_word:
        raise ValueError("word 不能为空")

    entry = (
        db.query(VocabularyEntry)
        .filter(
            VocabularyEntry.user_id == user_id, VocabularyEntry.word == normalized_word
        )
        .first()
    )

    if entry is None:
        entry = VocabularyEntry(
            user_id=user_id,
            article_id=article_id,
            word=normalized_word,
            pronunciation=_normalize_word(pronunciation or "") or None,
            meaning=_normalize_word(meaning or "") or None,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.add(entry)

    if pronunciation and not entry.pronunciation:
        entry.pronunciation = _normalize_word(pronunciation) or None
    if meaning and not entry.meaning:
        entry.meaning = _normalize_word(meaning) or None
    if article_id and entry.article_id is None:
        entry.article_id = article_id

    now = utc_now()
    entry.status = "mastered" if mastered else "learning"
    entry.mastered_at = now if mastered else None
    entry.updated_at = now
    db.commit()
    db.refresh(entry)
    return entry


def get_mastered_vocab_words(
    db: Session, user_id: int, words: Iterable[str]
) -> set[str]:
    normalized_words = [
        _normalize_word(word) for word in words if _normalize_word(word)
    ]
    if not normalized_words:
        return set()

    rows = (
        db.query(VocabularyEntry.word)
        .filter(
            VocabularyEntry.user_id == user_id,
            VocabularyEntry.word.in_(normalized_words),
            VocabularyEntry.status == "mastered",
        )
        .all()
    )
    return {row[0] for row in rows}


def attach_vocab_state(
    db: Session,
    user_id: int,
    vocab_items: list[dict],
) -> list[dict]:
    """给词汇列表补上 mastered 状态，供阅读页和生词本页面使用。"""
    normalized_words = [_normalize_word(item.get("word", "")) for item in vocab_items]
    state_map = get_mastered_vocab_words(db, user_id, normalized_words)

    enriched_items: list[dict] = []
    for item in vocab_items:
        word = _normalize_word(item.get("word", ""))
        enriched = dict(item)
        enriched["mastered"] = word in state_map
        enriched_items.append(enriched)

    return enriched_items


def list_vocabulary_entries(
    db: Session,
    user_id: int,
    status: str | None = None,
) -> list[VocabularyEntry]:
    query = db.query(VocabularyEntry).filter(VocabularyEntry.user_id == user_id)
    if status in {"learning", "mastered"}:
        query = query.filter(VocabularyEntry.status == status)
    return query.order_by(VocabularyEntry.updated_at.desc()).all()


def build_vocabulary_view_rows(
    db: Session,
    user_id: int,
    status: str | None = None,
) -> list[dict]:
    entries = list_vocabulary_entries(db, user_id, status)
    article_ids = [entry.article_id for entry in entries if entry.article_id]
    article_map: dict[int, str] = {}
    if article_ids:
        rows = (
            db.query(Article.id, Article.title)
            .filter(Article.id.in_(article_ids))
            .all()
        )
        article_map = {row[0]: row[1] for row in rows}

    view_rows: list[dict] = []
    for entry in entries:
        # pronunciation 字段现在存的是假名 reading (AI 给的优先, 旧条目为空)
        # romaji 由 pykakasi 机械从 reading 算出
        reading = entry.pronunciation or ""
        romaji = _reading_to_romaji(reading) if reading else ""
        view_rows.append(
            {
                "id": entry.id,
                "word": entry.word,
                "reading": reading,
                "romaji": romaji,
                # 兼容旧字段名 (vocabulary.js 仍读 pronunciation)
                "pronunciation": reading,
                "meaning": entry.meaning or "",
                "status": entry.status,
                "article_id": entry.article_id,
                "article_title": article_map.get(entry.article_id, ""),
                "updated_at": datetime_to_isoformat(entry.updated_at),
                "mastered_at": datetime_to_isoformat(entry.mastered_at),
            }
        )
    return view_rows
