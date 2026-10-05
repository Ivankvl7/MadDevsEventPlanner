"""Схемы запросов и ответов API."""

from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AfterValidator, AwareDatetime, BaseModel, EmailStr, Field, StringConstraints

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Description = Annotated[str, StringConstraints(max_length=5000)]
Capacity = Annotated[int, Field(ge=1, le=100_000)]
Password = Annotated[str, StringConstraints(min_length=8, max_length=128)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


def _check_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError, ValueError:
        raise ValueError("неизвестный часовой пояс") from None
    return value


TimezoneName = Annotated[str, AfterValidator(_check_timezone)]


class RegisterIn(BaseModel):
    email: EmailStr
    password: Password
    name: Name


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    name: str


class EventIn(BaseModel):
    title: Title
    description: Description = ""
    starts_at: AwareDatetime
    timezone: TimezoneName
    capacity: Capacity


class EventPatch(BaseModel):
    title: Title | None = None
    description: Description | None = None
    starts_at: AwareDatetime | None = None
    timezone: TimezoneName | None = None
    capacity: Capacity | None = None


class OrganizerOut(BaseModel):
    id: int
    name: str


class EventOut(BaseModel):
    id: int
    title: str
    description: str
    starts_at: datetime
    timezone: str
    capacity: int
    organizer: OrganizerOut
