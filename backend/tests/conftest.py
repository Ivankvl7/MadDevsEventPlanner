"""Общие фикстуры тестов.

Тесты идут на настоящей PostgreSQL (отдельная база), а не на SQLite:
блокировки и уникальные индексы должны проверяться по-настоящему.
Адрес тестовой базы — TEST_DATABASE_URL; база создаётся, если её нет.
"""

import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://eventplanner:eventplanner@localhost:5433/eventplanner_test",
)

# Подменяем адрес до импорта приложения: app.db создаёт engine при импорте.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL


def _ensure_database(url_str: str) -> None:
    url = make_url(url_str)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": url.database},
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()


_ensure_database(TEST_DATABASE_URL)
