"""Настройки приложения из переменных окружения.

Значения по умолчанию подходят только для локального запуска
и указывают на PostgreSQL из docker-compose (порт 5433 на хосте).
"""

import os

DEFAULT_DATABASE_URL = "postgresql+psycopg://eventplanner:eventplanner@localhost:5433/eventplanner"

DATABASE_URL: str = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)

SESSION_COOKIE = "ep_session"
SESSION_TTL_DAYS = 30
# Для локального запуска по http cookie не может быть Secure; за HTTPS включить COOKIE_SECURE=1.
COOKIE_SECURE: bool = os.environ.get("COOKIE_SECURE", "0") == "1"

# Фоновый цикл: напоминания и «доставка» писем (acceptance.md, R-9, R-15).
# В тестах выключен — там шаг цикла вызывается напрямую с подменённым временем.
SCHEDULER_ENABLED: bool = os.environ.get("SCHEDULER_ENABLED", "1") == "1"
SCHEDULER_INTERVAL_SECONDS: float = float(os.environ.get("SCHEDULER_INTERVAL_SECONDS", "30"))
