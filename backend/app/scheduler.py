"""Фоновые задачи: напоминания за сутки (B6) и «доставка» писем из outbox (R-15).

Расписание не хранится в памяти: каждый шаг выбирает работу по текущему состоянию БД.
Поэтому после перезапуска пропущенное досылается само (R-9, G6), а несколько экземпляров
backend не создают дублей: напоминания защищены ключом идемпотентности, письма на доставку
забираются через FOR UPDATE SKIP LOCKED.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock, mail, models
from app.db import SessionLocal
from app.models import RegistrationStatus as S

# Пишем в журнал uvicorn, чтобы «доставка» была видна в логах контейнера.
log = logging.getLogger("uvicorn.error")

REMINDER_BEFORE = timedelta(hours=24)
DELIVERY_BATCH = 100


def create_due_reminders(db: Session, now: datetime) -> int:
    """Напоминания всем confirmed, у кого до начала события ≤ 24 ч и оно ещё не началось.

    R-8: кто получил место уже внутри последних 24 ч, напоминание не получает — письмо
    с билетом пришло в тот же момент. Возвращает число созданных писем.
    """
    rows = db.execute(
        select(models.Registration, models.Event)
        .join(models.Event, models.Registration.event_id == models.Event.id)
        .where(
            models.Registration.status == S.CONFIRMED,
            models.Event.starts_at > now,
            models.Event.starts_at <= now + REMINDER_BEFORE,
            models.Registration.confirmed_at < models.Event.starts_at - REMINDER_BEFORE,
        )
        .order_by(models.Registration.id)
    ).all()
    created = sum(mail.send_reminder(db, reg, event) for reg, event in rows)
    db.commit()
    return created


def deliver_pending(db: Session, now: datetime) -> int:
    """«Отправить» пачку писем: в заглушке это отметка sent_at и строка в логе."""
    emails = db.scalars(
        select(models.OutboxEmail)
        .where(models.OutboxEmail.sent_at.is_(None))
        .order_by(models.OutboxEmail.id)
        .limit(DELIVERY_BATCH)
        .with_for_update(skip_locked=True)
    ).all()
    for email in emails:
        email.sent_at = now
        log.info("Почта (заглушка): %s → %s: %s", email.kind, email.to_email, email.subject)
    db.commit()
    return len(emails)


def run_once() -> tuple[int, int]:
    """Один шаг цикла. Возвращает (создано напоминаний, доставлено писем)."""
    with SessionLocal() as db:
        reminders = create_due_reminders(db, clock.now())
        delivered = 0
        while True:
            batch = deliver_pending(db, clock.now())
            delivered += batch
            if batch < DELIVERY_BATCH:
                break
    return reminders, delivered


async def run_forever(interval: float) -> None:
    """Цикл в процессе backend. Ошибка шага не останавливает цикл."""
    while True:
        try:
            await asyncio.to_thread(run_once)
        except Exception:
            log.exception("Ошибка фонового цикла")
        await asyncio.sleep(interval)
