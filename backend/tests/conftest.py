"""Общие фикстуры тестов.

Тесты идут на настоящей PostgreSQL (отдельная база), а не на SQLite:
блокировки и уникальные индексы должны проверяться по-настоящему.
Адрес тестовой базы — TEST_DATABASE_URL; база создаётся, если её нет,
схема пересоздаётся миграциями Alembic в начале прогона.
"""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://eventplanner:eventplanner@localhost:5433/eventplanner_test",
)

# Подменяем адрес до импорта приложения: app.db создаёт engine при импорте.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
# Фоновый цикл в тестах выключен: шаг вызывается напрямую с подменённым временем.
os.environ["SCHEDULER_ENABLED"] = "0"

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app import clock
from app.db import engine
from app.main import app

BACKEND_DIR = Path(__file__).resolve().parent.parent


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


@pytest.fixture(scope="session", autouse=True)
def _schema():
    """Чистая схема, созданная теми же миграциями, что и в рабочем запуске."""
    _ensure_database(TEST_DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    yield


@pytest.fixture(autouse=True)
def _clean_tables(_schema):
    yield
    with engine.begin() as conn:
        tables = conn.execute(
            text(
                "SELECT string_agg(quote_ident(tablename), ', ') FROM pg_tables "
                "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
            )
        ).scalar()
        if tables:
            conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


class FrozenClock:
    """Управляемое «сейчас» для тестов."""

    def __init__(self, start: datetime):
        self.current = start

    def __call__(self) -> datetime:
        return self.current

    def advance(self, **kwargs) -> None:
        self.current += timedelta(**kwargs)


@pytest.fixture
def frozen_clock(monkeypatch):
    fc = FrozenClock(datetime(2030, 1, 10, 12, 0, tzinfo=UTC))
    monkeypatch.setattr(clock, "now", fc)
    return fc


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def make_client():
    """Несколько независимых клиентов (у каждого свои cookie) — как разные пользователи."""
    clients = []

    def factory():
        c = TestClient(app)
        clients.append(c)
        return c

    yield factory
    for c in clients:
        c.close()


def register(c: TestClient, email: str, name: str = "Тест", password: str = "password123"):
    r = c.post("/api/auth/register", json={"email": email, "password": password, "name": name})
    assert r.status_code == 201, r.text
    return r.json()


def future(hours: float = 48) -> str:
    return (clock.now() + timedelta(hours=hours)).isoformat()
