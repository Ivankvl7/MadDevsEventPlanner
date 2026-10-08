"""Точка входа backend."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Annotated

from fastapi import Depends, FastAPI, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import config, scheduler
from app.db import get_db
from app.routers import auth, checkin, events, live, mail, registrations


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Фоновый цикл живёт столько же, сколько процесс backend."""
    task = None
    if config.SCHEDULER_ENABLED:
        task = asyncio.create_task(scheduler.run_forever(config.SCHEDULER_INTERVAL_SECONDS))
    yield
    if task is not None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="EventPlanner API", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(events.router)
app.include_router(registrations.router)
app.include_router(mail.router)
app.include_router(checkin.router)
app.include_router(live.router)


@app.get("/api/health")
def health(response: Response, db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    """Проверка, что backend запущен и видит базу данных."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "error", "database": "unavailable"}
    return {"status": "ok", "database": "ok"}
