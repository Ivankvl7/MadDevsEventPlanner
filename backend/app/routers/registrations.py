"""Регистрация на событие, отказ, «мои регистрации», списки участников для организатора."""

from datetime import UTC

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app import models, registrations
from app.deps import DB, CurrentUser
from app.models import RegistrationStatus as S
from app.routers.events import event_out, get_event_or_404
from app.schemas import (
    AttendeeCounts,
    AttendeesOut,
    ConfirmedAttendeeOut,
    MyRegistrationOut,
    RegistrationOut,
    WaitlistEntryOut,
)

router = APIRouter(prefix="/api", tags=["registrations"])


def registration_out(db: DB, reg: models.Registration) -> RegistrationOut:
    return RegistrationOut(
        id=reg.id,
        event_id=reg.event_id,
        status=reg.status,
        ticket_code=reg.ticket_code if reg.status == S.CONFIRMED else None,
        waitlist_position=registrations.waitlist_position(db, reg),
    )


@router.post("/events/{event_id}/registration")
def register(event_id: int, db: DB, user: CurrentUser, response: Response) -> RegistrationOut:
    """Записаться на событие email-ом своей учётной записи.

    201 — запись создана (или восстановлена после отказа), 200 — запись уже была.
    """
    reg, created = registrations.register(db, event_id, user)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return registration_out(db, reg)


@router.get("/events/{event_id}/registration")
def my_registration(event_id: int, db: DB, user: CurrentUser) -> RegistrationOut:
    reg = registrations.find_registration(db, event_id, user.email)
    if reg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Вы не зарегистрированы на это событие")
    return registration_out(db, reg)


@router.delete("/events/{event_id}/registration")
def cancel(event_id: int, db: DB, user: CurrentUser) -> RegistrationOut:
    return registration_out(db, registrations.cancel(db, event_id, user))


@router.get("/me/registrations")
def my_registrations(db: DB, user: CurrentUser) -> list[MyRegistrationOut]:
    regs = db.scalars(
        select(models.Registration)
        .options(joinedload(models.Registration.event).joinedload(models.Event.organizer))
        .join(models.Event)
        .where(models.Registration.user_id == user.id)
        .order_by(models.Event.starts_at)
    ).all()
    return [
        MyRegistrationOut(**registration_out(db, r).model_dump(), event=event_out(r.event))
        for r in regs
    ]


@router.get("/events/{event_id}/attendees")
def attendees(event_id: int, db: DB, user: CurrentUser) -> AttendeesOut:
    """F7: экран организатора — счётчики (записаны, в очереди, пришли), участники и очередь."""
    event = get_event_or_404(db, event_id)
    if event.organizer_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Список участников доступен организатору")
    rows = db.scalars(
        select(models.Registration)
        .options(joinedload(models.Registration.user))
        .where(
            models.Registration.event_id == event_id,
            models.Registration.status.in_([S.CONFIRMED, S.WAITLISTED]),
        )
        .order_by(models.Registration.confirmed_at, models.Registration.id)
    ).all()
    confirmed = [
        ConfirmedAttendeeOut(
            registration_id=r.id,
            name=r.user.name,
            email=r.email,
            since=r.confirmed_at.astimezone(UTC),
            checked_in_at=r.checked_in_at.astimezone(UTC) if r.checked_in_at else None,
        )
        for r in rows
        if r.status == S.CONFIRMED
    ]
    waiting = [r for r in rows if r.status == S.WAITLISTED]
    waitlist = [
        WaitlistEntryOut(
            registration_id=r.id,
            name=r.user.name,
            email=r.email,
            since=r.waitlisted_at.astimezone(UTC),
            position=i,
        )
        for i, r in enumerate(sorted(waiting, key=lambda r: r.waitlist_seq), start=1)
    ]
    return AttendeesOut(
        counts=AttendeeCounts(
            confirmed=len(confirmed),
            waitlisted=len(waitlist),
            # Считается из данных, а не отдельным счётчиком (acceptance.md, 5.4).
            checked_in=sum(1 for c in confirmed if c.checked_in_at is not None),
        ),
        confirmed=confirmed,
        waitlist=waitlist,
    )
