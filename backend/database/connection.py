import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

engine = None
SessionLocal = None


class DatabaseConfigurationError(RuntimeError):
    """Raised when a configured database cannot be initialized."""


def get_engine():
    """Initialize the optional database connection only when a DB route uses it."""
    global engine
    if not DATABASE_URL:
        return None
    if engine is not None:
        return engine
    try:
        engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    except Exception as exc:
        raise DatabaseConfigurationError(
            "DATABASE_URL is set, but its database driver or URL is invalid."
        ) from exc
    return engine


def get_db():
    global SessionLocal
    configured_engine = get_engine()
    if configured_engine is None:
        raise DatabaseConfigurationError(
            "DATABASE_URL is not configured; database-backed features are unavailable."
        )
    if SessionLocal is None:
        SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=configured_engine,
        )
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()