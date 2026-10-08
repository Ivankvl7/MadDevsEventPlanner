"""События: создание, просмотр, редактирование организатором."""

from datetime import UTC

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app import clock, live, mail, models, registrations
from app.deps import DB, CurrentUser
from app.models import RegistrationStatus as S
from app.schemas import EventIn, EventOut, EventPatch, OrganizerOut

router = APIRouter(prefix="/api/events", tags=["events"])


# Организатор загружается вместе с событием одним запросом.
_WITH_ORGANIZER = joinedload(models.Event.organizer)


def event_out(event: models.Event) -> EventOut:
    return EventOut(
        id=event.id,
        title=event.title,
        description=event.description,
        # Всегда UTC: клиент сам переводит в пояс браузера.
        starts_at=event.starts_at.astimezone(UTC),
        timezone=event.timezone,
        capacity=event.capacity,
        organizer=OrganizerOut(id=event.organizer.id, name=event.organizer.name),
    )


def get_event_or_404(db: DB, event_id: int) -> models.Event:
    event = db.scalar(
        select(models.Event).options(_WITH_ORGANIZER).where(models.Event.id == event_id)
    )
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Событие не найдено")
    return event


@router.get("")
def list_events(db: DB) -> list[EventOut]:
    events = db.scalars(
        select(models.Event).options(_WITH_ORGANIZER).order_by(models.Event.starts_at)
    )
    return [event_out(e) for e in events]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_event(data: EventIn, db: DB, user: CurrentUser) -> EventOut:
    if data.starts_at <= clock.now():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Дата события уже прошла")
    event = models.Event(organizer_id=user.id, **data.model_dump())
    db.add(event)
    db.commit()
    return event_out(get_event_or_404(db, event.id))


@router.get("/{event_id}")
def get_event(event_id: int, db: DB) -> EventOut:
    return event_out(get_event_or_404(db, event_id))


@router.patch("/{event_id}")
def update_event(event_id: int, data: EventPatch, db: DB, user: CurrentUser) -> EventOut:
    # Блокировка события: изменение лимита и перенос не пересекаются с регистрациями и отказами.
    event = registrations.lock_event(db, event_id)
    if event.organizer_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Изменять событие может только организатор")
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    now = clock.now()
    reschedule = "starts_at" in changes and changes["starts_at"] != event.starts_at
    if reschedule:
        # R-6: перенос в прошлое и перенос уже начавшегося события запрещены.
        if event.starts_at <= now:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Событие уже началось, перенос невозможен"
            )
        if changes["starts_at"] <= now:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Новая дата уже прошла")
    if "capacity" in changes:
        # R-10: уменьшать лимит ниже числа занятых мест нельзя — никого не выселяем.
        confirmed = registrations.count_by_status(db, event.id, S.CONFIRMED)
        if changes["capacity"] < confirmed:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Нельзя сделать лимит меньше числа занятых мест ({confirmed})",
            )

    old_start = mail.format_start(event)
    for field, value in changes.items():
        setattr(event, field, value)
    if reschedule:
        event.schedule_version += 1
        db.flush()
        for reg in registrations.active_registrations(db, event.id):
            mail.send_rescheduled(db, reg, event, old_start)
    # R-10: при увеличении лимита очередь продвигается сама.
    db.flush()
    registrations.promote(db, event, now)
    live.notify_event_changed(db, event.id)
    db.commit()
    return event_out(get_event_or_404(db, event.id))
