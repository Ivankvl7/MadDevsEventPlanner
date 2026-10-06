"""Конкурентные тесты (acceptance.md, 5.1–5.3).

Запросы идут параллельно из пула потоков; у каждого запроса своё соединение с БД.
Каждый сценарий повторяется несколько раз подряд на новом событии.
"""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import func, select

from app import models
from app.db import SessionLocal
from tests.conftest import register
from tests.test_registrations import create_event, emails, participant, reg_url

ROUNDS = 5


def parallel(method, url, clients):
    """Один и тот же запрос от каждого клиента одновременно."""
    with ThreadPoolExecutor(max_workers=len(clients)) as pool:
        return list(pool.map(lambda c: getattr(c, method)(url), clients))


def statuses(event_id):
    with SessionLocal() as db:
        return Counter(
            db.scalars(
                select(models.Registration.status).where(models.Registration.event_id == event_id)
            )
        )


def test_many_people_race_for_last_seat(client, make_client):
    """B5: 15 человек одновременно на одно свободное место."""
    register(client, "org@example.com")
    people = [participant(make_client, f"p{i}@example.com") for i in range(15)]

    for _ in range(ROUNDS):
        ev = create_event(client, capacity=1)
        results = parallel("post", reg_url(ev), people)

        assert [r.status_code for r in results] == [201] * 15
        assert Counter(r.json()["status"] for r in results) == {"confirmed": 1, "waitlisted": 14}
        positions = sorted(
            r.json()["waitlist_position"] for r in results if r.json()["status"] == "waitlisted"
        )
        assert positions == list(range(1, 15))  # очередь без пропусков и дублей
        assert statuses(ev) == {"confirmed": 1, "waitlisted": 14}
        event_mail = [m for m in emails() if m.event_id == ev]
        assert Counter(m.kind for m in event_mail) == {"ticket": 1, "waitlisted": 14}


def test_same_person_registers_many_times_in_parallel(client, make_client):
    """B2: двойной клик / несколько вкладок — одна запись, одно письмо."""
    register(client, "org@example.com")
    register(make_client(), "dup@example.com")
    tabs = []
    for _ in range(10):
        tab = make_client()
        r = tab.post(
            "/api/auth/login", json={"email": "dup@example.com", "password": "password123"}
        )
        assert r.status_code == 200
        tabs.append(tab)

    for _ in range(ROUNDS):
        ev = create_event(client, capacity=5)
        results = parallel("post", reg_url(ev), tabs)

        assert sorted(r.status_code for r in results) == [200] * 9 + [201]
        assert len({r.json()["id"] for r in results}) == 1
        assert len({r.json()["ticket_code"] for r in results}) == 1
        assert statuses(ev) == {"confirmed": 1}
        assert len([m for m in emails(to="dup@example.com") if m.event_id == ev]) == 1


def test_parallel_cancellations_promote_distinct_people(client, make_client):
    """5.3: несколько одновременных отказов продвигают столько же разных людей по порядку."""
    register(client, "org@example.com")
    people = [participant(make_client, f"p{i}@example.com") for i in range(8)]

    for _ in range(ROUNDS):
        ev = create_event(client, capacity=3)
        for p in people:  # по очереди: p0–p2 на местах, p3–p7 в очереди
            p.post(reg_url(ev))

        parallel("delete", reg_url(ev), people[:3])

        after = [p.get(reg_url(ev)).json() for p in people]
        assert [a["status"] for a in after] == ["cancelled"] * 3 + ["confirmed"] * 3 + [
            "waitlisted"
        ] * 2
        assert [a["waitlist_position"] for a in after[6:]] == [1, 2]
        promoted = [m.to_email for m in emails(kind="promoted") if m.event_id == ev]
        assert sorted(promoted) == ["p3@example.com", "p4@example.com", "p5@example.com"]


def test_parallel_repeated_cancel_promotes_once(client, make_client):
    """5.2: один и тот же отказ, отправленный много раз параллельно, освобождает одно место."""
    register(client, "org@example.com")
    register(make_client(), "leaver@example.com")
    tabs = []
    for _ in range(10):
        tab = make_client()
        tab.post("/api/auth/login", json={"email": "leaver@example.com", "password": "password123"})
        tabs.append(tab)
    waiting = [participant(make_client, f"w{i}@example.com") for i in range(2)]

    for _ in range(ROUNDS):
        ev = create_event(client, capacity=1)
        tabs[0].post(reg_url(ev))
        for w in waiting:
            w.post(reg_url(ev))

        results = parallel("delete", reg_url(ev), tabs)

        assert all(r.status_code == 200 for r in results)
        assert statuses(ev) == {"cancelled": 1, "confirmed": 1, "waitlisted": 1}
        assert waiting[0].get(reg_url(ev)).json()["status"] == "confirmed"
        assert waiting[1].get(reg_url(ev)).json()["waitlist_position"] == 1
        with SessionLocal() as db:
            promoted = db.scalar(
                select(func.count())
                .select_from(models.OutboxEmail)
                .where(models.OutboxEmail.event_id == ev, models.OutboxEmail.kind == "promoted")
            )
        assert promoted == 1
