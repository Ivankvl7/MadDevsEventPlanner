"""Почтовая заглушка: письма пишутся в таблицу outbox (R-15).

Письмо создаётся в транзакции вызывающего кода — вместе с изменением, которое его вызвало.
Уникальный ключ идемпотентности делает повторное создание того же письма no-op.
"""

from zoneinfo import ZoneInfo

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import models

TICKET = "ticket"
PROMOTED = "promoted"
WAITLISTED = "waitlisted"
RESCHEDULED = "rescheduled"


def format_start(event: models.Event) -> str:
    local = event.starts_at.astimezone(ZoneInfo(event.timezone))
    return f"{local:%d.%m.%Y %H:%M} ({event.timezone})"


def enqueue(
    db: Session,
    *,
    key: str,
    kind: str,
    reg: models.Registration,
    event: models.Event,
    subject: str,
    body: str,
) -> None:
    db.execute(
        insert(models.OutboxEmail)
        .values(
            idempotency_key=key,
            kind=kind,
            to_email=reg.email,
            event_id=event.id,
            registration_id=reg.id,
            subject=subject,
            body=body,
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
    )


def send_ticket(db: Session, reg: models.Registration, event: models.Event, *, promoted: bool):
    """B1 / B4: письмо с билетом. Ключ включает код — новый билет даёт новое письмо."""
    if promoted:
        kind, intro = PROMOTED, "Освободилось место — вы переведены из листа ожидания."
    else:
        kind, intro = TICKET, "Вы зарегистрированы."
    enqueue(
        db,
        key=f"ticket:{reg.id}:{reg.ticket_code}",
        kind=kind,
        reg=reg,
        event=event,
        subject=f"Билет: {event.title}",
        body=(
            f"{intro}\n\n"
            f"Событие: {event.title}\n"
            f"Начало: {format_start(event)}\n"
            f"Код билета: {reg.ticket_code}\n\n"
            "Назовите код на входе."
        ),
    )


def send_waitlisted(db: Session, reg: models.Registration, event: models.Event, position: int):
    """R-3: письмо о постановке в лист ожидания, без билета."""
    enqueue(
        db,
        key=f"waitlist:{reg.id}:{reg.waitlist_seq}",
        kind=WAITLISTED,
        reg=reg,
        event=event,
        subject=f"Лист ожидания: {event.title}",
        body=(
            "Свободных мест нет — вы в листе ожидания.\n\n"
            f"Событие: {event.title}\n"
            f"Начало: {format_start(event)}\n"
            f"Позиция в очереди: {position}\n\n"
            "Если место освободится, мы пришлём письмо с билетом."
        ),
    )


def send_rescheduled(db: Session, reg: models.Registration, event: models.Event, old_start: str):
    """B9 / R-6: письмо о переносе. Ключ — номер расписания события."""
    enqueue(
        db,
        key=f"reschedule:{event.id}:{event.schedule_version}:{reg.id}",
        kind=RESCHEDULED,
        reg=reg,
        event=event,
        subject=f"Перенос: {event.title}",
        body=(
            "Организатор перенёс событие.\n\n"
            f"Событие: {event.title}\n"
            f"Было: {old_start}\n"
            f"Стало: {format_start(event)}"
        ),
    )
