import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def _build_postgres_url() -> str:
    """
    Build a psycopg/SQLAlchemy connection URL using the environment variables exposed
    by the dedicated PostgreSQL container.

    Expected env vars (provided by platform):
    - POSTGRES_URL, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_PORT

    Notes:
    - Prefer POSTGRES_URL if it already contains a full SQLAlchemy/DSN style URL.
    - Otherwise build a URL from discrete parts.
    """
    raw_url = (os.getenv("POSTGRES_URL") or "").strip()
    if raw_url:
        # Allow either:
        # - postgresql://user:pass@host:port/db
        # - postgres://...
        # - postgresql+psycopg://...
        if raw_url.startswith("postgresql+psycopg://") or raw_url.startswith("postgresql://"):
            return raw_url
        if raw_url.startswith("postgres://"):
            return raw_url.replace("postgres://", "postgresql://", 1)
        # If POSTGRES_URL is provided but not in a known format, still attempt to use it.
        return raw_url

    user = os.getenv("POSTGRES_USER", "")
    password = os.getenv("POSTGRES_PASSWORD", "")
    db = os.getenv("POSTGRES_DB", "")
    port = os.getenv("POSTGRES_PORT", "5432")

    # Host is not provided as a separate env var in this template. In most Kavia DB containers,
    # POSTGRES_URL is the primary source and should be set. If it is not, we default to localhost.
    host = "localhost"

    if not user or not password or not db:
        raise RuntimeError(
            "PostgreSQL environment is not configured. Please set POSTGRES_URL "
            "or POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB."
        )

    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"


DATABASE_URL = _build_postgres_url()

# Using pool_pre_ping to gracefully handle stale connections in preview environments.
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# PUBLIC_INTERFACE
def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a SQLAlchemy session and ensures it is closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
