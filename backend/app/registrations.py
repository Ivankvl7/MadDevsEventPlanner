"""Регистрации: запись, отказ, лист ожидания, продвижение очереди.

Все изменения состава одного события выполняются в одной транзакции под блокировкой
строки события (SELECT … FOR UPDATE): регистрации, отказы, продвижение и изменение лимита
одного события идут строго по очереди, разные события друг друга не блокируют
(acceptance.md, 5.1–5.3). Решение «место или лист ожидания» принимается внутри блокировки.
"""

import secrets
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import clock, mail, models
from app.models import RegistrationStatus as S

# R-16: без похожих символов (0/O, 1/I/L).
TICKET_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
TICKET_LENGTH = 10


def new_ticket_code() -> str:
    return "".join(secrets.choice(TICKET_ALPHABET) for _ in range(TICKET_LENGTH))


def lock_event(db: Session, event_id: int) -> models.Event:
    event = db.scalar(
        select(models.Event)
        .where(models.Event.id == event_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Событие не найдено")
    return event


def count_by_status(db: Session, event_id: int, reg_status: str) -> int:
    return db.scalar(
        select(func.count())
        .select_from(models.Registration)
        .where(models.Registration.event_id == event_id, models.Registration.status == reg_status)
    )


def waitlist_position(db: Session, reg: models.Registration) -> int | None:
    """Позиция в очереди, начиная с 1 (R-4)."""
    if reg.status != S.WAITLISTED:
        return None
    return db.scalar(
        select(func.count())
        .select_from(models.Registration)
        .where(
            models.Registration.event_id == reg.event_id,
            models.Registration.status == S.WAITLISTED,
            models.Registration.waitlist_seq <= reg.waitlist_seq,
        )
    )


def find_registration(
    db: Session, event_id: int, email: str, *, for_update: bool = False
) -> models.Registration | None:
    query = select(models.Registration).where(
        models.Registration.event_id == event_id, models.Registration.email == email
    )
    if for_update:
        query = query.with_for_update().execution_options(populate_existing=True)
    return db.scalar(query)


def _confirm(reg: models.Registration, now: datetime) -> None:
    reg.status = S.CONFIRMED
    reg.ticket_code = new_ticket_code()
    reg.confirmed_at = now
    reg.waitlist_seq = None


def _put_on_waitlist(db: Session, reg: models.Registration, now: datetime) -> None:
    reg.status = S.WAITLISTED
    reg.ticket_code = None  # прежний код после отказа больше не действует (R-2)
    reg.waitlist_seq = db.scalar(models.waitlist_seq.next_value())
    reg.waitlisted_at = now


def _started(event: models.Event, now: datetime) -> bool:
    return event.starts_at <= now


def register(db: Session, event_id: int, user: models.User) -> tuple[models.Registration, bool]:
    """F2, B2, B3, R-2. Возвращает (запись, создана ли или реактивирована сейчас)."""
    now = clock.now()
    event = lock_event(db, event_id)
    if _started(event, now):
        raise HTTPException(status.HTTP_409_CONFLICT, "Событие уже началось, регистрация закрыта")

    reg = find_registration(db, event_id, user.email)
    if reg is not None and reg.status != S.CANCELLED:
        # Повторная регистрация: ничего не меняем, писем не шлём.
        db.commit()  # только снять блокировку
        return reg, False
    if reg is None:
        reg = models.Registration(event_id=event_id, user_id=user.id, email=user.email)
        db.add(reg)

    if count_by_status(db, event_id, S.CONFIRMED) < event.capacity:
        _confirm(reg, now)
        db.flush()
        mail.send_ticket(db, reg, event, promoted=False)
    else:
        _put_on_waitlist(db, reg, now)
        db.flush()
        mail.send_waitlisted(db, reg, event, waitlist_position(db, reg))
    db.commit()
    return reg, True


def cancel(db: Session, event_id: int, user: models.User) -> models.Registration:
    """F3, R-5. Повторный отказ ничего не меняет; освободившееся место уходит очереди (B4)."""
    now = clock.now()
    event = lock_event(db, event_id)
    # Блокировка строки записи: отказ не пересечётся с одновременным чекином этого билета.
    reg = find_registration(db, event_id, user.email, for_update=True)
    if reg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Вы не зарегистрированы на это событие")
    if reg.status == S.CANCELLED:
        db.commit()  # только снять блокировку
        return reg
    if _started(event, now):
        raise HTTPException(status.HTTP_409_CONFLICT, "Событие уже началось, отказ невозможен")
    if reg.checked_in_at is not None:
        # R-11: отказ после чекина запрещён.
        raise HTTPException(status.HTTP_409_CONFLICT, "Вы уже отмечены на входе, отказ невозможен")

    freed_seat = reg.status == S.CONFIRMED
    reg.status = S.CANCELLED
    reg.cancelled_at = now
    reg.waitlist_seq = None
    db.flush()
    if freed_seat:
        promote(db, event, now)
    db.commit()
    return reg


def promote(db: Session, event: models.Event, now: datetime) -> None:
    """Отдать свободные места первым в очереди (R-4), каждому — письмо с билетом.

    Вызывается под блокировкой события. После начала события очередь не двигается (R-11).
    """
    if _started(event, now):
        return
    free = event.capacity - count_by_status(db, event.id, S.CONFIRMED)
    if free <= 0:
        return
    promoted = db.scalars(
        select(models.Registration)
        .where(
            models.Registration.event_id == event.id,
            models.Registration.status == S.WAITLISTED,
        )
        .order_by(models.Registration.waitlist_seq)
        .limit(free)
    ).all()
    for reg in promoted:
        _confirm(reg, now)
    db.flush()
    for reg in promoted:
        mail.send_ticket(db, reg, event, promoted=True)


def active_registrations(db: Session, event_id: int) -> list[models.Registration]:
    """Участники для письма о переносе (R-6): confirmed и waitlisted."""
    return db.scalars(
        select(models.Registration)
        .where(
            models.Registration.event_id == event_id,
            models.Registration.status.in_([S.CONFIRMED, S.WAITLISTED]),
        )
        .order_by(models.Registration.id)
    ).all()
