"""Fixtures compartilhadas: banco SQLite isolado por teste."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import create_db_engine, get_engine, get_sessionmaker, init_db

# fixture `user` do NiceGUI (simula o navegador nos testes de interface)
pytest_plugins = ["nicegui.testing.user_plugin"]

REFERENCE_NOW = datetime(2026, 11, 18, 14, 0, 0)  # quarta-feira


@pytest.fixture
def session() -> Iterator[Session]:
    """Sessão ligada a um banco novo em memória."""
    engine = create_db_engine("sqlite://")
    init_db(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def _clear_caches() -> None:
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


@pytest.fixture
def app_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Aponta a aplicação inteira (engine padrão) para um banco temporário.

    Deve vir **antes** da fixture ``user`` na assinatura do teste.
    """
    monkeypatch.setenv("PF_DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    _clear_caches()
    yield
    get_engine().dispose()
    _clear_caches()
