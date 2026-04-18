"""SQLAlchemy 2.0 engine + session factory. Used by the cache and persistence layer.

The MVP only stores the HTTP cache and benchmark history; domain entities are
serialized to JSON files. A minimal declarative base is provided so future
persistence layers can extend it without a migration.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    """Root SQLAlchemy declarative base."""


def _db_path() -> Path:
    cache_dir = get_settings().resolved_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "app.db"


def get_engine(url: str | None = None) -> "object":  # return typed as Any to avoid import in api
    """Create an engine. Uses SQLite at the resolved cache dir by default."""
    from sqlalchemy.engine import Engine

    final_url = url or f"sqlite:///{_db_path()}"
    engine: Engine = create_engine(final_url, future=True)
    Base.metadata.create_all(engine)
    return engine


_SessionLocal: sessionmaker[Session] | None = None


def _factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),  # type: ignore[arg-type]
            autoflush=False,
            expire_on_commit=False,
            future=True,
        )
    return _SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for a series of operations."""
    session = _factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
