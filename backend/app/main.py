"""Точка входа backend."""

from typing import Annotated

from fastapi import Depends, FastAPI, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import get_db
from app.routers import auth, events, mail, registrations

app = FastAPI(title="EventPlanner API")
app.include_router(auth.router)
app.include_router(events.router)
app.include_router(registrations.router)
app.include_router(mail.router)


@app.get("/api/health")
def health(response: Response, db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    """Проверка, что backend запущен и видит базу данных."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "error", "database": "unavailable"}
    return {"status": "ok", "database": "ok"}
