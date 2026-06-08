from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, UniqueConstraint, Boolean
from sqlalchemy.orm import relationship
from app.db import Base
from app.utils.time import utc_now


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    level = Column(Integer, default=1, nullable=False)  # 用户能力等级
    # AI配置字段
    openai_api_key = Column(String(500), nullable=True)
    openai_base_url = Column(String(500), nullable=True)
    openai_model = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    articles = relationship("Article", back_populates="user", cascade="all, delete-orphan")
    vocabulary_entries = relationship("VocabularyEntry", back_populates="user", cascade="all, delete-orphan")


class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    emoji_cover = Column(String(255), nullable=True)
    original = Column(Text, nullable=False)
    ruby_html = Column(Text, nullable=False)
    translation = Column(Text, nullable=False)
    vocab_json = Column(Text, nullable=False)
    source_url = Column(String(500), nullable=True)  # 源URL字段
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, nullable=False)

    user = relationship("User", back_populates="articles")
    vocabulary_entries = relationship("VocabularyEntry", back_populates="article", cascade="all, delete-orphan")


class VocabularyEntry(Base):
    __tablename__ = "vocabulary_entries"
    __table_args__ = (
        UniqueConstraint("user_id", "word", name="uq_vocabulary_entries_user_word"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=True, index=True)
    word = Column(String(255), nullable=False)
    pronunciation = Column(String(255), nullable=True)
    meaning = Column(Text, nullable=True)
    status = Column(String(50), default="learning", nullable=False)  # learning, mastered
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, nullable=False)
    mastered_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="vocabulary_entries")
    article = relationship("Article", back_populates="vocabulary_entries")


class CrawlTask(Base):
    __tablename__ = "crawl_tasks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(50), default="pending", nullable=False)  # pending, processing, completed, failed
    total_articles = Column(Integer, default=0, nullable=False)
    processed_articles = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, nullable=False)

    user = relationship("User")


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "type", "source_task_id", name="uq_notifications_user_type_task"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(50), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    source_task_id = Column(Integer, nullable=True, index=True)
    source_url = Column(String(500), nullable=True)
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, nullable=False)

    user = relationship("User")
