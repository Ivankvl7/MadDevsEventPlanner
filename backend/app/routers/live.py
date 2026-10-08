"""Live-поток экрана организатора (B8, R-14): Server-Sent Events.

Клиент открывает EventSource. Сервер сразу шлёт текущий снимок экрана, а затем новый снимок
после каждого изменения состава события. После обрыва EventSource переподключается сам и снова
получает актуальный снимок первым сообщением, поэтому пропущенное во время разрыва не теряется
(acceptance.md, 5.6).
"""

import asyncio
from collections.abc import AsyncIterator

import psycopg
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app import live, models
from app.db import SessionLocal
from app.deps import SessionCookie, user_by_token
from app.routers.registrations import attendees_snapshot

router = APIRouter(prefix="/api/events", tags=["live"])


def _authorize(event_id: int, session_token: str | None) -> None:
    # Своя короткая сессия БД: соединение из пула не занято, пока открыт поток.
    with SessionLocal() as db:
        user = user_by_token(db, session_token)
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Требуется вход")
        event = db.get(models.Event, event_id)
        if event is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Событие не найдено")
        if event.organizer_id != user.id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Список участников доступен организатору"
            )


def _snapshot_json(event_id: int) -> str:
    with SessionLocal() as db:
        return attendees_snapshot(db, event_id).model_dump_json()


def _message(data: str) -> str:
    return f"event: attendees\ndata: {data}\n\n"


async def _stream(event_id: int, request: Request) -> AsyncIterator[str]:
    async with await psycopg.AsyncConnection.connect(live.listen_dsn(), autocommit=True) as conn:
        await conn.execute(f"LISTEN {live.CHANNEL}")
        # Первый снимок — уже после LISTEN: изменение между ними не потеряется.
        yield _message(await asyncio.to_thread(_snapshot_json, event_id))
        while not await request.is_disconnected():
            changed = False
            async for note in conn.notifies(timeout=live.HEARTBEAT_SECONDS):
                if note.payload == str(event_id):
                    changed = True
                    break
            if changed:
                yield _message(await asyncio.to_thread(_snapshot_json, event_id))
            else:
                yield ": ping\n\n"


@router.get("/{event_id}/attendees/live")
async def attendees_live(
    event_id: int, request: Request, session_token: SessionCookie = None
) -> StreamingResponse:
    """Поток `text/event-stream`: события `attendees` с тем же JSON, что `GET …/attendees`."""
    await asyncio.to_thread(_authorize, event_id, session_token)
    return StreamingResponse(
        _stream(event_id, request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
