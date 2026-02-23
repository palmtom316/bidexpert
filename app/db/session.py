from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

_engine_kwargs: dict = {"future": True}
if "sqlite" not in settings.database_url:
    _engine_kwargs.update(
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=settings.db_pool_pre_ping,
        pool_recycle=settings.db_pool_recycle,
    )
engine = create_engine(settings.database_url, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


def _bootstrap_sqlite_schema() -> None:
    """Ensure local sqlite schema exists for direct service/test entrypoints."""
    if engine.dialect.name != "sqlite":
        return

    from app.db.base import Base
    from app.models import tables as _tables  # noqa: F401

    Base.metadata.create_all(bind=engine)


_bootstrap_sqlite_schema()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    except Exception:  # noqa: BLE001
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    except Exception:  # noqa: BLE001
        db.rollback()
        raise
    finally:
        db.close()
