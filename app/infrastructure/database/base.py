"""
Declarative Base
================
Single declarative base for all SQLAlchemy ORM models.
Import this base in every model file.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass
