from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.model.models import Article, User, VocabularyEntry
from app.services.vocabulary import seed_vocabulary_entries, get_mastered_vocab_words
from app.utils.time import utc_now


@contextmanager
def make_session():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def test_seed_vocabulary_entries_creates_one_row_per_word():
    with make_session() as db:
        user = User(email='test@example.com', password_hash='hash')
        article = Article(
            user_id=1,
            title='标题',
            original='原文',
            ruby_html='ruby',
            translation='翻译',
            vocab_json='[]',
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.add(user)
        db.flush()
        article.user_id = user.id
        db.add(article)
        db.flush()

        created = seed_vocabulary_entries(
            db,
            user_id=user.id,
            article_id=article.id,
            vocab_items=[
                {'word': '天気', 'pronunciation': 'てんき', 'meaning': '天气'},
                {'word': '天気', 'pronunciation': 'てんき', 'meaning': '天气'},
            ],
        )

        assert created == 1
        rows = db.query(VocabularyEntry).all()
        assert len(rows) == 1
        assert rows[0].word == '天気'
        assert rows[0].status == 'learning'


def test_seed_vocabulary_entries_preserves_mastered_state():
    with make_session() as db:
        user = User(email='test@example.com', password_hash='hash')
        article = Article(
            user_id=1,
            title='标题',
            original='原文',
            ruby_html='ruby',
            translation='翻译',
            vocab_json='[]',
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.add(user)
        db.flush()
        article.user_id = user.id
        db.add(article)
        db.flush()

        entry = VocabularyEntry(
            user_id=user.id,
            article_id=article.id,
            word='天気',
            pronunciation='てんき',
            meaning='天气',
            status='mastered',
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.add(entry)
        db.commit()

        created = seed_vocabulary_entries(
            db,
            user_id=user.id,
            article_id=article.id,
            vocab_items=[{'word': '天気', 'pronunciation': 'てんき', 'meaning': '天气'}],
        )

        assert created == 0
        persisted = db.query(VocabularyEntry).one()
        assert persisted.status == 'mastered'


def test_get_mastered_vocab_words_filters_by_input_words():
    with make_session() as db:
        user = User(email='test@example.com', password_hash='hash')
        db.add(user)
        db.flush()

        db.add(
            VocabularyEntry(
                user_id=user.id,
                word='天気',
                pronunciation='てんき',
                meaning='天气',
                status='mastered',
                created_at=utc_now(),
                updated_at=utc_now(),
            )
        )
        db.commit()

        result = get_mastered_vocab_words(db, user.id, ['天気', '学校'])

        assert result == {'天気'}
