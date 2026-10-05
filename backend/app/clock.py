"""Источник текущего времени.

Вынесен в отдельную функцию, чтобы тесты могли подменять «сейчас»
(окно чекина, напоминания за сутки).
"""

from datetime import UTC, datetime


def now() -> datetime:
    return datetime.now(UTC)
