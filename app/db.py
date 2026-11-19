"""Engine, sessões e criação do schema."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.models import Base
from app.services.text import simplify


def _configure_sqlite_connection(dbapi_connection: Any, _record: Any) -> None:
    """Liga chaves estrangeiras e registra ``pf_simplify`` (busca sem acento/caixa)."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
    dbapi_connection.create_function("pf_simplify", 1, simplify, deterministic=True)


def create_db_engine(url: str | None = None) -> Engine:
    """Cria uma engine SQLAlchemy.

    Para SQLite: cria a pasta do arquivo, liga ``foreign_keys`` e, em memória,
    usa ``StaticPool`` para que todas as sessões vejam o mesmo banco.
    """
    url = url or get_settings().database_url
    kwargs: dict[str, Any] = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url or url == "sqlite://":
            kwargs["poolclass"] = StaticPool
        else:
            Path(url.split("///", 1)[1]).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        event.listen(engine, "connect", _configure_sqlite_connection)
    return engine


def init_db(engine: Engine) -> None:
    """Cria todas as tabelas que ainda não existem."""
    Base.metadata.create_all(engine)


def drop_db(engine: Engine) -> None:
    """Remove todas as tabelas (usado pelo ``seed --reset``)."""
    Base.metadata.drop_all(engine)


@lru_cache
def get_engine() -> Engine:
    """Engine padrão da aplicação (cacheada)."""
    return create_db_engine()


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    """Fábrica de sessões ligada à engine padrão."""
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Sessão transacional: commit ao final, rollback em caso de erro."""
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
