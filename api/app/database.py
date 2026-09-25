"""SQLAlchemy engine + session factory."""
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    pass


_settings = get_settings()

# pool_pre_ping avoids stale-connection errors when MySQL restarts
engine = create_engine(
    _settings.database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a session that closes on exit."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context manager for non-request usage (e.g. seed, worker)."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()