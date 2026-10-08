"""Live-обновления экрана организатора (B8, R-14): PostgreSQL LISTEN/NOTIFY + SSE.

Изменение состава события (регистрация, отказ, продвижение, изменение события, чекин)
публикует NOTIFY в той же транзакции — сигнал доходит только после фиксации, поэтому клиент
не увидит незафиксированных данных. Работает и при нескольких процессах backend.
"""

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app import config

CHANNEL = "event_changes"
# Комментарий SSE раз в N секунд: держит соединение через прокси и выявляет закрытые вкладки.
HEARTBEAT_SECONDS = 15.0


def notify_event_changed(db: Session, event_id: int) -> None:
    """Сигнал «у события изменились счётчики или списки». Уходит при COMMIT."""
    db.execute(
        text("SELECT pg_notify(:channel, :payload)"), {"channel": CHANNEL, "payload": str(event_id)}
    )


def listen_dsn() -> str:
    """Адрес БД для psycopg без префикса драйвера SQLAlchemy."""
    url = make_url(config.DATABASE_URL).set(drivername="postgresql")
    return url.render_as_string(hide_password=False)
