"""Чекин на входе: ввод кода билета вместо сканера (F6, B7, R-11)."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import joinedload

from app import clock, live, models
from app.deps import DB, CurrentUser
from app.models import RegistrationStatus as S
from app.routers.events import get_event_or_404
from app.schemas import CheckinIn, CheckinOut

router = APIRouter(prefix="/api/events", tags=["checkin"])

CHECKIN_OPENS_BEFORE = timedelta(hours=3)


def checkin_window(event: models.Event) -> tuple[datetime, datetime]:
    """R-11: с T−3 ч до конца календарного дня начала события в его часовом поясе."""
    tz = ZoneInfo(event.timezone)
    start_day = event.starts_at.astimezone(tz).date()
    closes = datetime.combine(start_day + timedelta(days=1), time(0), tzinfo=tz)
    return event.starts_at - CHECKIN_OPENS_BEFORE, closes


def normalize_code(code: str) -> str:
    """Регистр и пробелы при вводе не важны (R-16)."""
    return "".join(code.split()).upper()


def _local(moment: datetime, event: models.Event) -> datetime:
    return moment.astimezone(ZoneInfo(event.timezone))


@router.post("/{event_id}/checkin")
def checkin(event_id: int, data: CheckinIn, db: DB, user: CurrentUser) -> CheckinOut:
    event = get_event_or_404(db, event_id)
    if event.organizer_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Чекин доступен только организатору")
    now = clock.now()
    opens, closes = checkin_window(event)
    if now < opens:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Чекин откроется {_local(opens, event):%d.%m.%Y в %H:%M} ({event.timezone})",
        )
    if now >= closes:
        raise HTTPException(status.HTTP_409_CONFLICT, "Чекин закрыт: день события закончился")

    code = normalize_code(data.code)
    # Атомарная отметка: из параллельных запросов строку обновит ровно один (acceptance.md, 5.4).
    reg_id = db.execute(
        update(models.Registration)
        .where(
            models.Registration.ticket_code == code,
            models.Registration.event_id == event.id,
            models.Registration.status == S.CONFIRMED,
            models.Registration.checked_in_at.is_(None),
        )
        .values(checked_in_at=now)
        .returning(models.Registration.id)
        .execution_options(synchronize_session=False)
    ).scalar()
    if reg_id is None:
        db.rollback()
        raise _rejection(db, event, code)
    live.notify_event_changed(db, event.id)
    db.commit()

    reg = db.scalar(
        select(models.Registration)
        .options(joinedload(models.Registration.user))
        .where(models.Registration.id == reg_id)
    )
    return CheckinOut(
        registration_id=reg.id,
        name=reg.user.name,
        email=reg.email,
        event_id=event.id,
        event_title=event.title,
        checked_in_at=reg.checked_in_at.astimezone(UTC),
    )


def _rejection(db: DB, event: models.Event, code: str) -> HTTPException:
    """Понятная причина отказа (F6)."""
    reg = db.scalar(select(models.Registration).where(models.Registration.ticket_code == code))
    if reg is None:
        return HTTPException(status.HTTP_404_NOT_FOUND, "Билет не найден")
    if reg.event_id != event.id:
        return HTTPException(status.HTTP_409_CONFLICT, "Билет на другое событие")
    if reg.status == S.CANCELLED:
        return HTTPException(status.HTTP_409_CONFLICT, "Билет отменён: участник отказался")
    if reg.checked_in_at is not None:
        return HTTPException(
            status.HTTP_409_CONFLICT,
            f"Билет уже отмечен в {_local(reg.checked_in_at, event):%H:%M}",
        )
    return HTTPException(status.HTTP_409_CONFLICT, "Билет недействителен")
