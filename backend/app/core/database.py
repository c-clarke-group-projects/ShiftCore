"""Shared metadata and environment-based database configuration."""

import os

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """All application table models inherit from this base."""


def get_database_url() -> str:
    """Read configuration when needed, keeping credentials outside source code."""

    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise ValueError("Set DATABASE_URL before running database migrations")
    return url
