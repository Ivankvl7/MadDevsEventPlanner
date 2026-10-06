"""Схема БД (SQLAlchemy 2). Изменения схемы — только через миграции Alembic."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Sequence,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Хранится нормализованным (trim + lower); уникальность — на уровне БД.
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Session(Base):
    """Серверная сессия. Хранится SHA-256 токена, сам токен — только в cookie."""

    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (CheckConstraint("capacity > 0", name="capacity_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organizer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # IANA-пояс события: нужен для границы «конец дня события» в окне чекина (R-11, R-13).
    timezone: Mapped[str] = mapped_column(String(64))
    capacity: Mapped[int]
    # Номер расписания: растёт при каждом переносе, входит в ключ письма о переносе —
    # повторный перенос (даже обратно на прежнюю дату) даёт новые письма (R-7).
    schedule_version: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    organizer: Mapped[User] = relationship()


class RegistrationStatus:
    CONFIRMED = "confirmed"
    WAITLISTED = "waitlisted"
    CANCELLED = "cancelled"


# Порядок постановки в лист ожидания. Последовательность строго возрастает
# и не зависит от точности часов: реактивированная запись всегда встаёт в конец (R-4).
waitlist_seq = Sequence("registrations_waitlist_seq")


class Registration(Base):
    """Запись участника на событие. Одна строка на пару (событие, email) — B2."""

    __tablename__ = "registrations"
    __table_args__ = (
        UniqueConstraint("event_id", "email", name="uq_registrations_event_email"),
        CheckConstraint(
            "status IN ('confirmed', 'waitlisted', 'cancelled')", name="registration_status"
        ),
        CheckConstraint(
            "status <> 'confirmed' OR ticket_code IS NOT NULL", name="confirmed_has_ticket"
        ),
        CheckConstraint(
            "status <> 'waitlisted' OR waitlist_seq IS NOT NULL", name="waitlisted_has_seq"
        ),
        Index("ix_registrations_event_status", "event_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # Email учётной записи на момент регистрации, нормализованный (R-1).
    email: Mapped[str] = mapped_column(String(320))
    status: Mapped[str] = mapped_column(String(16))
    # Код билета (R-16). У отменённой записи код сохраняется, чтобы чекин мог ответить
    # «билет отменён»; при повторной регистрации выдаётся новый код (R-2).
    ticket_code: Mapped[str | None] = mapped_column(String(10), unique=True)
    waitlist_seq: Mapped[int | None] = mapped_column(BigInteger)
    waitlisted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    event: Mapped[Event] = relationship()
    user: Mapped[User] = relationship()


class OutboxEmail(Base):
    """Почтовая заглушка (R-15): письмо создаётся в той же транзакции, что и его причина.

    idempotency_key уникален — повторное создание того же письма ничего не делает.
    """

    __tablename__ = "outbox_emails"

    id: Mapped[int] = mapped_column(primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    kind: Mapped[str] = mapped_column(String(32))
    to_email: Mapped[str] = mapped_column(String(320), index=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    registration_id: Mapped[int | None] = mapped_column(
        ForeignKey("registrations.id", ondelete="CASCADE")
    )
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Заполняется фоновым «доставщиком» (следующие этапы).
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
