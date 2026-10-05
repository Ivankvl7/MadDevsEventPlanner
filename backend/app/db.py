"""Подключение к PostgreSQL."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app import config

engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI-зависимость: сессия БД на время запроса."""
    with SessionLocal() as session:
        yield session
