"""
Database Connection
===================
Creates the SQLAlchemy engine and session factory.
All database models inherit from the declarative base defined in base.py.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings

settings = get_settings()

# ── Engine ───────────────────────────────────────────────────────────────────
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,       # Verify connections before use
    pool_size=10,             # Max persistent connections
    max_overflow=20,          # Extra connections under load
    pool_recycle=3600,        # Recycle connections after 1 hour
    echo=settings.APP_DEBUG,  # Log SQL when debugging
)

# ── Session Factory ──────────────────────────────────────────────────────────
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)
