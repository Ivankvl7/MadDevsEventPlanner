"""Фоновый цикл: напоминания за сутки (B6, R-7…R-9) и «доставка» писем (R-15, G4, G6).

Шаг цикла вызывается напрямую с подменённым временем: «сейчас» = 2030-01-10 12:00 UTC.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi.testclient import TestClient
from sqlalchemy import select

from app import clock, config, models, scheduler
from app.db import SessionLocal
from app.main import app
from tests.conftest import future, register
from tests.test_registrations import create_event, emails, participant, reg_url


def reminders(to=None):
    return emails(to=to, kind="reminder")


def test_reminder_once_when_less_than_a_day_left(client, make_client, frozen_clock):
    """B6: ровно одно напоминание, повторные шаги дублей не создают."""
    register(client, "org@example.com")
    ev = create_event(client, hours=48)
    alice = participant(make_client, "alice@example.com")
    code = alice.post(reg_url(ev)).json()["ticket_code"]

    assert scheduler.run_once()[0] == 0  # до начала 48 ч — рано
    frozen_clock.advance(hours=23, minutes=59)
    assert scheduler.run_once()[0] == 0  # 24 ч 1 мин — ещё рано
    frozen_clock.advance(minutes=1)
    assert scheduler.run_once()[0] == 1  # ровно 24 ч
    for _ in range(3):
        frozen_clock.advance(hours=1)
        assert scheduler.run_once()[0] == 0

    [mail] = reminders(to="alice@example.com")
    assert code in mail.body and "Митап" in mail.body


def test_reminder_only_for_confirmed(client, make_client, frozen_clock):
    """B6, R-8: не тем, кто в очереди, и не отказавшимся."""
    register(client, "org@example.com")
    ev = create_event(client, capacity=2, hours=48)
    a, b, c = (participant(make_client, f"{n}@example.com") for n in "abc")
    for p in (a, b, c):
        p.post(reg_url(ev))
    b.delete(reg_url(ev))  # место b уходит c — заранее, за 48 ч

    frozen_clock.advance(hours=30)
    scheduler.run_once()
    assert sorted(m.to_email for m in reminders()) == ["a@example.com", "c@example.com"]


def test_no_reminder_for_seat_received_within_last_day(client, make_client, frozen_clock):
    """R-8: место получено уже внутри последних 24 ч — хватит письма с билетом."""
    register(client, "org@example.com")
    ev = create_event(client, capacity=1, hours=48)
    a, b = (participant(make_client, f"{n}@example.com") for n in "ab")
    a.post(reg_url(ev))
    b.post(reg_url(ev))

    frozen_clock.advance(hours=30)  # до начала 18 ч
    a.delete(reg_url(ev))  # b продвинут сейчас
    late = participant(make_client, "late@example.com")
    org_capacity = client.patch(f"/api/events/{ev}", json={"capacity": 2})
    assert org_capacity.status_code == 200
    late.post(reg_url(ev))  # записался внутри суток

    scheduler.run_once()
    assert reminders() == []
    assert len(emails(to="b@example.com", kind="promoted")) == 1
    assert len(emails(to="late@example.com", kind="ticket")) == 1


def test_missed_reminders_after_downtime(client, make_client, frozen_clock):
    """R-9: цикл не работал — после старта досылает, если событие ещё не началось."""
    register(client, "org@example.com")
    soon = create_event(client, hours=48)
    started = create_event(client, hours=30)
    alice = participant(make_client, "alice@example.com")
    alice.post(reg_url(soon))
    alice.post(reg_url(started))

    frozen_clock.advance(hours=47)  # «сервер лежал» почти двое суток
    assert scheduler.run_once()[0] == 1
    [mail] = reminders()
    assert mail.event_id == soon  # по уже начавшемуся событию — не шлём


def test_reschedule_gives_new_reminder_for_new_date(client, make_client, frozen_clock):
    """R-7: напоминание ушло, событие перенесли — по новой дате будет ещё одно."""
    register(client, "org@example.com")
    ev = create_event(client, hours=48)
    alice = participant(make_client, "alice@example.com")
    alice.post(reg_url(ev))

    frozen_clock.advance(hours=30)
    scheduler.run_once()
    assert len(reminders()) == 1

    client.patch(f"/api/events/{ev}", json={"starts_at": future(72)})
    assert len(emails(kind="rescheduled")) == 1
    scheduler.run_once()
    assert len(reminders()) == 1  # до новой даты ещё 72 ч

    frozen_clock.advance(hours=48)
    scheduler.run_once()
    scheduler.run_once()
    assert len(reminders()) == 2
    assert "Начало: 15.01.2030" in reminders()[-1].body


def test_delivery_marks_every_email_sent_once(client, make_client, frozen_clock):
    """R-15, G4: письма из outbox «доставляются», статус виден на странице почты."""
    register(client, "org@example.com")
    ev = create_event(client, capacity=1)
    a, b = (participant(make_client, f"{n}@example.com") for n in "ab")
    a.post(reg_url(ev))
    b.post(reg_url(ev))

    assert [m["sent_at"] for m in a.get("/api/mail").json()] == [None]
    assert scheduler.run_once() == (0, 2)
    assert a.get("/api/mail").json()[0]["sent_at"].startswith("2030-01-10T12:00:00")
    assert scheduler.run_once() == (0, 0)


def test_parallel_scheduler_instances_do_not_duplicate(client, make_client, frozen_clock):
    """B6, 5.5: несколько экземпляров цикла одновременно — по одному напоминанию,
    каждое письмо «доставлено» ровно одним экземпляром."""
    register(client, "org@example.com")
    ev = create_event(client, capacity=20, hours=48)
    people = [participant(make_client, f"p{i}@example.com") for i in range(20)]
    for p in people:
        p.post(reg_url(ev))
    scheduler.run_once()  # доставить письма с билетами
    frozen_clock.advance(hours=30)

    created = delivered = 0
    for _ in range(5):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: scheduler.run_once(), range(8)))
        created += sum(r[0] for r in results)
        delivered += sum(r[1] for r in results)
        frozen_clock.advance(minutes=1)
    delivered += scheduler.run_once()[1]
    assert created == delivered == 20

    assert sorted(m.to_email for m in reminders()) == sorted(f"p{i}@example.com" for i in range(20))
    assert all(m.sent_at is not None for m in emails())


def test_background_loop_runs_inside_backend(monkeypatch, client, make_client):
    """G6: цикл стартует вместе с backend и сам «доставляет» письма (реальное время)."""
    register(client, "org@example.com")
    ev = create_event(client)
    alice = participant(make_client, "alice@example.com")
    alice.post(reg_url(ev))

    monkeypatch.setattr(config, "SCHEDULER_ENABLED", True)
    monkeypatch.setattr(config, "SCHEDULER_INTERVAL_SECONDS", 0.1)
    with TestClient(app):  # запуск lifespan, как при старте uvicorn
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with SessionLocal() as db:
                pending = db.scalars(
                    select(models.OutboxEmail).where(models.OutboxEmail.sent_at.is_(None))
                ).all()
            if not pending:
                break
            time.sleep(0.05)
    assert pending == []


def test_parallel_delivery_takes_each_email_once(client, frozen_clock):
    """5.5: экземпляры, стартующие одновременно, делят письма без пересечений (SKIP LOCKED)."""
    register(client, "org@example.com")
    ev = create_event(client)
    with SessionLocal() as db:
        db.add_all(
            models.OutboxEmail(
                idempotency_key=f"test:{i}",
                kind="test",
                to_email="x@example.com",
                event_id=ev,
                subject="s",
                body="b",
            )
            for i in range(1000)
        )
        db.commit()

    start = Barrier(8)

    def instance(_):
        start.wait()
        total = 0
        with SessionLocal() as db:
            while batch := scheduler.deliver_pending(db, clock.now()):
                total += batch
        return total

    with ThreadPoolExecutor(max_workers=8) as pool:
        totals = list(pool.map(instance, range(8)))
    assert sum(totals) == 1000
    assert len([t for t in totals if t]) > 1  # работу действительно делили
