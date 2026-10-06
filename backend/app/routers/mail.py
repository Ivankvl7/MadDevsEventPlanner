"""Почтовая заглушка: просмотр писем, «отправленных» текущему пользователю (G4)."""

from datetime import UTC

from fastapi import APIRouter
from sqlalchemy import select

from app import models
from app.deps import DB, CurrentUser
from app.schemas import MailOut

router = APIRouter(prefix="/api/mail", tags=["mail"])


@router.get("")
def my_mail(db: DB, user: CurrentUser) -> list[MailOut]:
    # Письма содержат коды билетов, поэтому каждый видит только свои.
    emails = db.scalars(
        select(models.OutboxEmail)
        .where(models.OutboxEmail.to_email == user.email)
        .order_by(models.OutboxEmail.id.desc())
    )
    return [
        MailOut(
            id=e.id,
            kind=e.kind,
            to_email=e.to_email,
            event_id=e.event_id,
            subject=e.subject,
            body=e.body,
            created_at=e.created_at.astimezone(UTC),
        )
        for e in emails
    ]
