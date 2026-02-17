from app.db.base import Base
from app.db.session import engine
from app.models import tables  # noqa: F401


def init_db() -> None:
    """Initialize local SQLite schema for development/tests.

    PostgreSQL schema changes are managed exclusively by Alembic migrations.
    """
    if engine.dialect.name == "sqlite":
        Base.metadata.create_all(bind=engine)
