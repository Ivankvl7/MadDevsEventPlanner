"""Общие зависимости FastAPI: БД и текущий пользователь."""

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock, config, models
from app.db import get_db
from app.security import token_hash

DB = Annotated[Session, Depends(get_db)]


# Cookie сессии ставит и отправляет браузер; в Swagger поле не показываем — оно сбивает с толку.
SessionCookie = Annotated[str | None, Cookie(alias=config.SESSION_COOKIE, include_in_schema=False)]


def user_by_token(db: Session, session_token: str | None) -> models.User | None:
    if not session_token:
        return None
    return db.scalar(
        select(models.User)
        .join(models.Session, models.Session.user_id == models.User.id)
        .where(
            models.Session.token_hash == token_hash(session_token),
            models.Session.expires_at > clock.now(),
        )
    )


def optional_user(db: DB, session_token: SessionCookie = None) -> models.User | None:
    return user_by_token(db, session_token)


def current_user(
    user: Annotated[models.User | None, Depends(optional_user)],
) -> models.User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Требуется вход")
    return user


CurrentUser = Annotated[models.User, Depends(current_user)]
OptionalUser = Annotated[models.User | None, Depends(optional_user)]
