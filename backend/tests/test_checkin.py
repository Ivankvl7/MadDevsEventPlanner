"""Чекин (F6, B7, R-11) и счётчик «пришло» (F7).

Время подменено: «сейчас» = 2030-01-10 12:00 UTC. Событие начинается 11.01 в 15:00 по Бишкеку
(09:00 UTC); окно чекина — с 12:00 по Бишкеку (06:00 UTC) до конца 11.01 по Бишкеку (18:00 UTC).
"""

from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.conftest import register
from tests.test_registrations import participant, reg_url

START = "2030-01-11T15:00:00+06:00"


@pytest.fixture
def setup(client, make_client, frozen_clock):
    """Организатор (client), событие на 2 места, участники a и b с билетами, c в очереди."""
    register(client, "org@example.com", name="Организатор")
    r = client.post(
        "/api/events",
        json={"title": "Митап", "starts_at": START, "timezone": "Asia/Bishkek", "capacity": 2},
    )
    ev = r.json()["id"]
    people = {n: participant(make_client, f"{n}@example.com") for n in "abc"}
    codes = {n: p.post(reg_url(ev)).json()["ticket_code"] for n, p in people.items()}
    return ev, people, codes


def checkin_url(ev):
    return f"/api/events/{ev}/checkin"


def open_window(frozen_clock):
    frozen_clock.advance(hours=18)  # 2030-01-11 06:00 UTC = T−3 ч


def counts(client, ev):
    return client.get(f"/api/events/{ev}/attendees").json()["counts"]


def test_successful_checkin(client, setup, frozen_clock):
    ev, _, codes = setup
    open_window(frozen_clock)
    # Регистр и пробелы при вводе не важны.
    typed = " ".join([codes["a"][:5].lower(), codes["a"][5:]])
    r = client.post(checkin_url(ev), json={"code": typed})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["name"], body["email"]) == ("a", "a@example.com")
    assert (body["event_id"], body["event_title"]) == (ev, "Митап")
    assert body["checked_in_at"].startswith("2030-01-11T06:00:00")

    assert counts(client, ev) == {"confirmed": 2, "waitlisted": 1, "checked_in": 1}
    data = client.get(f"/api/events/{ev}/attendees").json()
    assert [x["checked_in_at"] is not None for x in data["confirmed"]] == [True, False]


def test_ticket_passes_only_once(client, setup, frozen_clock):
    """B7: второй чекин отклоняется с временем первого (в поясе события)."""
    ev, _, codes = setup
    open_window(frozen_clock)
    assert client.post(checkin_url(ev), json={"code": codes["a"]}).status_code == 200
    frozen_clock.advance(minutes=7)
    again = client.post(checkin_url(ev), json={"code": codes["a"]})
    assert again.status_code == 409
    assert again.json()["detail"] == "Билет уже отмечен в 12:00"
    assert counts(client, ev)["checked_in"] == 1


def test_checkin_window(client, setup, frozen_clock):
    """R-11: с T−3 ч до конца календарного дня события в его часовом поясе."""
    ev, _, codes = setup
    frozen_clock.advance(hours=17, minutes=59)  # за минуту до открытия
    early = client.post(checkin_url(ev), json={"code": codes["a"]})
    assert early.status_code == 409
    assert early.json()["detail"] == "Чекин откроется 11.01.2030 в 12:00 (Asia/Bishkek)"

    frozen_clock.advance(minutes=1)
    assert client.post(checkin_url(ev), json={"code": codes["a"]}).status_code == 200

    frozen_clock.advance(hours=11, minutes=59)  # 23:59 по Бишкеку — ещё открыт
    assert client.post(checkin_url(ev), json={"code": codes["b"]}).status_code == 200

    frozen_clock.advance(minutes=1)  # полночь по Бишкеку — закрыт
    late = client.post(checkin_url(ev), json={"code": codes["a"]})
    assert late.status_code == 409
    assert late.json()["detail"] == "Чекин закрыт: день события закончился"


def test_rejection_reasons(client, make_client, setup, frozen_clock):
    """F6: не найден, другое событие, отменён; код листа ожидания и старый код недействительны."""
    ev, people, codes = setup
    other = client.post(
        "/api/events",
        json={"title": "Другое", "starts_at": START, "timezone": "Asia/Bishkek", "capacity": 5},
    ).json()["id"]
    other_code = people["a"].post(reg_url(other)).json()["ticket_code"]

    old_code = codes["b"]
    people["b"].delete(reg_url(ev))  # место b переходит c
    open_window(frozen_clock)

    def reason(code):
        r = client.post(checkin_url(ev), json={"code": code})
        return r.status_code, r.json()["detail"]

    assert reason("AAAAAAAAAA") == (404, "Билет не найден")
    assert reason(other_code) == (409, "Билет на другое событие")
    assert reason(old_code) == (409, "Билет отменён: участник отказался")
    assert client.post(checkin_url(ev), json={"code": "  "}).status_code == 422
    assert counts(client, ev)["checked_in"] == 0

    # Повторная регистрация после отказа: новый билет проходит, старый — уже нет.
    frozen_clock.advance(hours=-18)
    people["c"].delete(reg_url(ev))  # освобождаем место для b
    new_code = people["b"].post(reg_url(ev)).json()["ticket_code"]
    open_window(frozen_clock)
    assert reason(old_code) == (404, "Билет не найден")
    assert client.post(checkin_url(ev), json={"code": new_code}).status_code == 200


def test_only_event_organizer_can_check_in(client, make_client, setup, frozen_clock):
    ev, people, codes = setup
    open_window(frozen_clock)
    assert people["a"].post(checkin_url(ev), json={"code": codes["a"]}).status_code == 403
    assert make_client().post(checkin_url(ev), json={"code": codes["a"]}).status_code == 401
    assert client.post(checkin_url(999), json={"code": codes["a"]}).status_code == 404
    assert counts(client, ev)["checked_in"] == 0


def test_no_cancel_after_checkin(client, setup, frozen_clock):
    """R-11: отказ после чекина запрещён; место не уходит очереди."""
    ev, people, codes = setup
    open_window(frozen_clock)  # чекин открыт, событие ещё не началось
    client.post(checkin_url(ev), json={"code": codes["a"]})
    r = people["a"].delete(reg_url(ev))
    assert r.status_code == 409
    assert people["a"].get(reg_url(ev)).json()["status"] == "confirmed"
    assert people["c"].get(reg_url(ev)).json()["status"] == "waitlisted"


def test_parallel_checkins_of_one_ticket(client, make_client, setup, frozen_clock):
    """B7, 5.4: два контролёра одновременно — ровно один успех, счётчик 1."""
    ev, _, codes = setup
    open_window(frozen_clock)
    # Вкладки организатора: отдельные клиенты с одной учётной записью.
    tabs = []
    for _ in range(10):
        tab = make_client()
        tab.post("/api/auth/login", json={"email": "org@example.com", "password": "password123"})
        tabs.append(tab)

    for code in (codes["a"], codes["b"]):
        with ThreadPoolExecutor(max_workers=len(tabs)) as pool:
            results = list(
                pool.map(lambda t: t.post(checkin_url(ev), json={"code": code}), tabs)  # noqa: B023
            )
        assert sorted(r.status_code for r in results) == [200] + [409] * 9
        assert all("уже отмечен" in r.json()["detail"] for r in results if r.status_code == 409)
    assert counts(client, ev)["checked_in"] == 2


def test_parallel_cancel_and_checkin(client, make_client, frozen_clock):
    """Отказ и чекин одного билета одновременно: побеждает ровно одно действие."""
    register(client, "org@example.com")
    people = [participant(make_client, f"p{i}@example.com") for i in range(10)]
    outcomes = set()
    for _ in range(5):
        ev = client.post(
            "/api/events",
            json={"title": "X", "starts_at": START, "timezone": "Asia/Bishkek", "capacity": 10},
        ).json()["id"]
        codes = [p.post(reg_url(ev)).json()["ticket_code"] for p in people]
        open_window(frozen_clock)

        def checkin(code, ev=ev):
            return client.post(checkin_url(ev), json={"code": code}).status_code

        def cancel(p, ev=ev):
            return p.delete(reg_url(ev)).status_code

        with ThreadPoolExecutor(max_workers=20) as pool:
            checkins = [pool.submit(checkin, c) for c in codes]
            cancels = [pool.submit(cancel, p) for p in people]
        for p, ci, ca in zip(people, checkins, cancels, strict=True):
            pair = (ci.result(), ca.result())
            assert pair in {(200, 409), (409, 200)}, pair
            outcomes.add(pair)
            reg = p.get(reg_url(ev)).json()
            assert reg["status"] == ("confirmed" if pair[0] == 200 else "cancelled")
        assert counts(client, ev)["checked_in"] == sum(c.result() == 200 for c in checkins)
        frozen_clock.advance(hours=-18)
