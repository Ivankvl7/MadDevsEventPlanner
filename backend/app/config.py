"""Настройки приложения из переменных окружения.

Значения по умолчанию подходят только для локального запуска
и указывают на PostgreSQL из docker-compose (порт 5433 на хосте).
"""

import os

DEFAULT_DATABASE_URL = "postgresql+psycopg://eventplanner:eventplanner@localhost:5433/eventplanner"

DATABASE_URL: str = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
