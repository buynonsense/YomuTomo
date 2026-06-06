from __future__ import annotations

import importlib.util
import pathlib
import sys
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker


def _load_app_package() -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    package_root = repo_root / 'app'
    init_file = package_root / '__init__.py'

    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)

    if 'app' in sys.modules and getattr(sys.modules['app'], '__path__', None):
        return

    spec = importlib.util.spec_from_file_location(
        'app',
        init_file,
        submodule_search_locations=[str(package_root)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError('无法加载 app 包')

    module = importlib.util.module_from_spec(spec)
    sys.modules['app'] = module
    spec.loader.exec_module(module)


_load_app_package()


@pytest.fixture()
def test_engine(monkeypatch: pytest.MonkeyPatch):
    from app import db as app_db
    from app import main as app_main

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    monkeypatch.setattr(app_db, "engine", engine)
    monkeypatch.setattr(app_main, "engine", engine)
    monkeypatch.setattr(app_db, "SessionLocal", sessionmaker(autocommit=False, autoflush=False, bind=engine))
    return engine


@pytest.fixture()
def db_session(test_engine):
    from app.db import Base

    Base.metadata.create_all(bind=test_engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        test_engine.dispose()


@pytest.fixture()
def client(test_engine, db_session, monkeypatch: pytest.MonkeyPatch):
    from app import main as app_main
    from app.db import get_db

    def override_get_db() -> Generator:
        try:
            yield db_session
        finally:
            pass

    app_main.app.dependency_overrides[get_db] = override_get_db
    with TestClient(app_main.app) as test_client:
        yield test_client
    app_main.app.dependency_overrides.clear()
