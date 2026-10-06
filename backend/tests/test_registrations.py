from sqlalchemy import func, select

from app import models
from app.db import SessionLocal
from app.registrations import TICKET_ALPHABET, TICKET_LENGTH
from tests.conftest import future, register


def create_event(c, capacity=10, hours=48):
    r = c.post(
        "/api/events",
        json={
            "title": "Митап",
            "description": "Описание",
            "starts_at": future(hours),
            "timezone": "Asia/Bishkek",
            "capacity": capacity,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def participant(make_client, email):
    c = make_client()
    register(c, email, name=email.split("@")[0])
    return c


def emails(to=None, kind=None):
    with SessionLocal() as db:
        q = select(models.OutboxEmail).order_by(models.OutboxEmail.id)
        if to:
            q = q.where(models.OutboxEmail.to_email == to)
        if kind:
            q = q.where(models.OutboxEmail.kind == kind)
        return db.scalars(q).all()


def registrations_count(event_id):
    with SessionLocal() as db:
        return db.scalar(
            select(func.count())
            .select_from(models.Registration)
            .where(models.Registration.event_id == event_id)
        )


def reg_url(event_id):
    return f"/api/events/{event_id}/registration"


def test_registration_requires_login_and_existing_event(client, make_client, frozen_clock):
    register(client, "org@example.com")
    ev = create_event(client)
    assert make_client().post(reg_url(ev)).status_code == 401
    assert client.post(reg_url(999)).status_code == 404
    assert client.delete(reg_url(ev)).status_code == 404  # отказ без регистрации


def test_confirmed_registration_gets_ticket_and_one_email(client, make_client, frozen_clock):
    register(client, "org@example.com")
    ev = create_event(client)
    alice = participant(make_client, "Alice@Example.com")

    r = alice.post(reg_url(ev))
    assert r.status_code == 201
    reg = r.json()
    assert reg["status"] == "confirmed"
    assert reg["waitlist_position"] is None
    code = reg["ticket_code"]
    assert len(code) == TICKET_LENGTH and set(code) <= set(TICKET_ALPHABET)

    # B1: ровно одно письмо, с кодом и данными события.
    [mail] = emails(to="alice@example.com")
    assert mail.kind == "ticket"
    assert code in mail.body and "Митап" in mail.body

    assert alice.get(reg_url(ev)).json() == reg
    [mine] = alice.get("/api/me/registrations").json()
    assert mine["ticket_code"] == code
    assert mine["event"]["id"] == ev

    # Письмо видно в заглушке только адресату.
    assert [m["id"] for m in alice.get("/api/mail").json()] == [mail.id]
    assert client.get("/api/mail").json() == []


def test_repeat_registration_changes_nothing(client, make_client, frozen_clock):
    """B2, R-2: повторный запрос возвращает ту же запись, без второго места и письма."""
    register(client, "org@example.com")
    ev = create_event(client)
    alice = participant(make_client, "alice@example.com")

    first = alice.post(reg_url(ev))
    second = alice.post(reg_url(ev))
    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json() == second.json()
    assert registrations_count(ev) == 1
    assert len(emails(to="alice@example.com")) == 1


def test_full_event_puts_new_registrations_on_waitlist(client, make_client, frozen_clock):
    """B3, F4, R-3."""
    register(client, "org@example.com")
    ev = create_event(client, capacity=1)
    a, b, c = (participant(make_client, f"{n}@example.com") for n in "abc")

    assert a.post(reg_url(ev)).json()["status"] == "confirmed"
    rb = b.post(reg_url(ev)).json()
    rc = c.post(reg_url(ev)).json()
    assert (rb["status"], rb["waitlist_position"], rb["ticket_code"]) == ("waitlisted", 1, None)
    assert (rc["status"], rc["waitlist_position"]) == ("waitlisted", 2)

    [mail] = emails(to="c@example.com")
    assert mail.kind == "waitlisted"
    assert "Позиция в очереди: 2" in mail.body


def test_cancel_promotes_first_in_waitlist(client, make_client, frozen_clock):
    """F3, B4: место уходит первому в очереди, он получает билет и ровно одно письмо."""
    register(client, "org@example.com")
    ev = create_event(client, capacity=1)
    a, b, c = (participant(make_client, f"{n}@example.com") for n in "abc")
    for p in (a, b, c):
        p.post(reg_url(ev))

    r = a.delete(reg_url(ev))
    assert r.status_code == 200
    assert (r.json()["status"], r.json()["ticket_code"]) == ("cancelled", None)

    rb = b.get(reg_url(ev)).json()
    assert rb["status"] == "confirmed" and rb["ticket_code"]
    [promoted] = emails(to="b@example.com", kind="promoted")
    assert rb["ticket_code"] in promoted.body
    assert c.get(reg_url(ev)).json()["waitlist_position"] == 1

    # Повторный отказ ничего не меняет и очередь второй раз не двигает.
    assert a.delete(reg_url(ev)).json()["status"] == "cancelled"
    assert c.get(reg_url(ev)).json()["status"] == "waitlisted"
    assert emails(to="c@example.com", kind="promoted") == []


def test_cancel_from_waitlist_does_not_promote(client, make_client, frozen_clock):
    """R-5."""
    register(client, "org@example.com")
    ev = create_event(client, capacity=1)
    a, b, c = (participant(make_client, f"{n}@example.com") for n in "abc")
    for p in (a, b, c):
        p.post(reg_url(ev))

    assert b.delete(reg_url(ev)).json()["status"] == "cancelled"
    assert a.get(reg_url(ev)).json()["status"] == "confirmed"
    assert c.get(reg_url(ev)).json()["waitlist_position"] == 1
    assert emails(kind="promoted") == []


def test_reregistration_after_cancel(client, make_client, frozen_clock):
    """R-2: новый код билета при свободном месте; при полном событии — в конец очереди."""
    register(client, "org@example.com")
    ev = create_event(client, capacity=1)
    a, b, c = (participant(make_client, f"{n}@example.com") for n in "abc")

    old_code = a.post(reg_url(ev)).json()["ticket_code"]
    a.delete(reg_url(ev))
    again = a.post(reg_url(ev))
    assert again.status_code == 201
    assert again.json()["status"] == "confirmed"
    assert again.json()["ticket_code"] != old_code
    assert len(emails(to="a@example.com", kind="ticket")) == 2
    assert registrations_count(ev) == 1

    b.post(reg_url(ev))
    c.post(reg_url(ev))
    b.delete(reg_url(ev))
    back = b.post(reg_url(ev)).json()
    assert (back["status"], back["waitlist_position"]) == ("waitlisted", 2)
    assert c.get(reg_url(ev)).json()["waitlist_position"] == 1


def test_capacity_change_rules(client, make_client, frozen_clock):
    """R-10: уменьшить ниже занятых мест нельзя; увеличение продвигает очередь."""
    register(client, "org@example.com")
    ev = create_event(client, capacity=2)
    ps = [participant(make_client, f"p{i}@example.com") for i in range(5)]
    for p in ps:
        p.post(reg_url(ev))

    r = client.patch(f"/api/events/{ev}", json={"capacity": 1})
    assert r.status_code == 409
    assert "(2)" in r.json()["detail"]

    assert client.patch(f"/api/events/{ev}", json={"capacity": 4}).status_code == 200
    statuses = [p.get(reg_url(ev)).json() for p in ps]
    assert [s["status"] for s in statuses] == ["confirmed"] * 4 + ["waitlisted"]
    assert statuses[4]["waitlist_position"] == 1
    assert [m.to_email for m in emails(kind="promoted")] == ["p2@example.com", "p3@example.com"]

    # Уменьшение до числа занятых мест разрешено.
    assert client.patch(f"/api/events/{ev}", json={"capacity": 4}).status_code == 200


def test_no_registration_or_cancel_after_start(client, make_client, frozen_clock):
    """R-11: после начала события запись и отказ закрыты, очередь не двигается."""
    register(client, "org@example.com")
    ev = create_event(client, capacity=1, hours=2)
    a, b, c = (participant(make_client, f"{n}@example.com") for n in "abc")
    a.post(reg_url(ev))
    b.post(reg_url(ev))

    frozen_clock.advance(hours=3)
    assert c.post(reg_url(ev)).status_code == 409
    assert a.delete(reg_url(ev)).status_code == 409
    assert client.patch(f"/api/events/{ev}", json={"capacity": 5}).status_code == 200
    assert b.get(reg_url(ev)).json()["status"] == "waitlisted"


def test_reschedule_notifies_active_participants(client, make_client, frozen_clock):
    """B9, R-6: письмо confirmed и waitlisted, не отказавшимся; на каждый перенос."""
    register(client, "org@example.com")
    ev = create_event(client, capacity=1)
    a, b, c = (participant(make_client, f"{n}@example.com") for n in "abc")
    for p in (a, b, c):
        p.post(reg_url(ev))
    c.delete(reg_url(ev))
    url = f"/api/events/{ev}"
    original = client.get(url).json()["starts_at"]

    assert client.patch(url, json={"description": "Новое описание"}).status_code == 200
    assert client.patch(url, json={"starts_at": original}).status_code == 200  # та же дата
    assert emails(kind="rescheduled") == []

    assert client.patch(url, json={"starts_at": future(72)}).status_code == 200
    first = emails(kind="rescheduled")
    assert sorted(m.to_email for m in first) == ["a@example.com", "b@example.com"]
    assert "Стало:" in first[0].body

    # Перенос обратно на прежнюю дату — снова по одному письму.
    assert client.patch(url, json={"starts_at": original}).status_code == 200
    assert len(emails(kind="rescheduled")) == 4


def test_attendees_screen(client, make_client, frozen_clock):
    """F7, F8: счётчики и списки видит только организатор."""
    register(client, "org@example.com")
    ev = create_event(client, capacity=2)
    ps = [participant(make_client, f"p{i}@example.com") for i in range(4)]
    for p in ps:
        p.post(reg_url(ev))
    ps[0].delete(reg_url(ev))  # p2 продвинут, p3 остаётся в очереди

    r = client.get(f"/api/events/{ev}/attendees")
    assert r.status_code == 200
    data = r.json()
    assert data["counts"] == {"confirmed": 2, "waitlisted": 1}
    assert [x["email"] for x in data["confirmed"]] == ["p1@example.com", "p2@example.com"]
    assert [(x["email"], x["position"]) for x in data["waitlist"]] == [("p3@example.com", 1)]
    assert data["confirmed"][0]["name"] == "p1"

    assert ps[1].get(f"/api/events/{ev}/attendees").status_code == 403
    assert make_client().get(f"/api/events/{ev}/attendees").status_code == 401


def test_organizer_can_register_for_own_event(client, frozen_clock):
    """R-12."""
    register(client, "org@example.com")
    ev = create_event(client)
    assert client.post(reg_url(ev)).json()["status"] == "confirmed"
