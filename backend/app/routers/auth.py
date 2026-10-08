"""Учётные записи: регистрация, вход, выход, текущий пользователь."""

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app import clock, config, models
from app.deps import DB, CurrentUser, SessionCookie
from app.schemas import LoginIn, RegisterIn, UserOut
from app.security import (
    hash_password,
    new_session_token,
    normalize_email,
    token_hash,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_out(user: models.User) -> UserOut:
    return UserOut(id=user.id, email=user.email, name=user.name)


def _start_session(db: DB, response: Response, user: models.User) -> None:
    token = new_session_token()
    ttl = timedelta(days=config.SESSION_TTL_DAYS)
    db.add(
        models.Session(token_hash=token_hash(token), user_id=user.id, expires_at=clock.now() + ttl)
    )
    db.commit()
    response.set_cookie(
        config.SESSION_COOKIE,
        token,
        max_age=int(ttl.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=config.COOKIE_SECURE,
        path="/",
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(data: RegisterIn, db: DB, response: Response) -> UserOut:
    user = models.User(
        email=normalize_email(data.email),
        name=data.name,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Пользователь с таким email уже существует"
        ) from None
    _start_session(db, response, user)
    return _user_out(user)


@router.post("/login")
def login(data: LoginIn, db: DB, response: Response) -> UserOut:
    user = db.scalar(select(models.User).where(models.User.email == normalize_email(data.email)))
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный email или пароль")
    _start_session(db, response, user)
    return _user_out(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    db: DB,
    response: Response,
    session_token: SessionCookie = None,
) -> None:
    if session_token:
        db.execute(
            delete(models.Session).where(models.Session.token_hash == token_hash(session_token))
        )
        db.commit()
    response.delete_cookie(config.SESSION_COOKIE, path="/")


@router.get("/me")
def me(user: CurrentUser) -> UserOut:
    return _user_out(user)
