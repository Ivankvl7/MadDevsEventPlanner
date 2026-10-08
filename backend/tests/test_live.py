"""Live-обновления экрана организатора (B8, G5, R-14) через настоящий HTTP-сервер.

SSE проверяется на запущенном uvicorn: поток читается отдельным HTTP-клиентом, а изменения
делаются другими клиентами — как две вкладки браузера. Время реальное.
"""

import json
import socket
import threading
import time
from datetime import UTC, datetime, timedelta

import httpx2
import pytest
import uvicorn
from sqlalchemy import text

from app import live
from app.db import engine
from app.main import app
from tests.conftest import register
from tests.test_registrations import participant, reg_url


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setattr(live, "HEARTBEAT_SECONDS", 0.3)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = uvicorn.Server(
        uvicorn.Config(
            app, host="127.0.0.1", port=port, log_level="warning", timeout_graceful_shutdown=2
        )
    )
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    while not srv.started:
        time.sleep(0.02)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    thread.join(timeout=10)


class Stream:
    """Чтение событий SSE с таймаутом; комментарии-пинги пропускаются."""

    def __init__(self, base_url, token, event_id):
        self.client = httpx2.Client(base_url=base_url, cookies={"ep_session": token}, timeout=5)
        self.cm = self.client.stream("GET", f"/api/events/{event_id}/attendees/live")
        self.response = self.cm.__enter__()
        assert self.response.status_code == 200
        assert self.response.headers["content-type"].startswith("text/event-stream")
        self.lines = self.response.iter_lines()

    def next_snapshot(self, wait=5.0):
        # Пинги приходят постоянно, поэтому ждём данные не дольше wait секунд.
        deadline = time.monotonic() + wait
        for line in self.lines:
            if line.startswith("data: "):
                return json.loads(line.removeprefix("data: "))
            if time.monotonic() > deadline:
                raise AssertionError("снимок не пришёл")
        raise AssertionError("поток закрылся")

    def close(self):
        self.cm.__exit__(None, None, None)
        self.client.close()


def make_event(c, capacity=5):
    starts = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    r = c.post(
        "/api/events",
        json={"title": "Live", "starts_at": starts, "timezone": "UTC", "capacity": capacity},
    )
    return r.json()["id"]


def token(c):
    return c.cookies.get("ep_session")


def test_counter_updates_without_reload(server, client, make_client):
    """B8: экран открыт в одной «вкладке», чекин — в другой; счётчик меняется сам."""
    register(client, "org@example.com")
    ev = make_event(client)
    alice = participant(make_client, "alice@example.com")
    code = alice.post(reg_url(ev)).json()["ticket_code"]

    screen = Stream(server, token(client), ev)
    try:
        first = screen.next_snapshot()
        assert first["counts"] == {"confirmed": 1, "waitlisted": 0, "checked_in": 0}

        assert client.post(f"/api/events/{ev}/checkin", json={"code": code}).status_code == 200
        assert screen.next_snapshot()["counts"]["checked_in"] == 1

        bob = participant(make_client, "bob@example.com")
        bob.post(reg_url(ev))
        assert screen.next_snapshot()["counts"]["confirmed"] == 2

        bob.delete(reg_url(ev))
        assert screen.next_snapshot()["counts"]["confirmed"] == 1
    finally:
        screen.close()


def test_other_events_do_not_trigger_updates(server, client, make_client):
    register(client, "org@example.com")
    ev, other = make_event(client), make_event(client)
    alice = participant(make_client, "alice@example.com")

    screen = Stream(server, token(client), ev)
    try:
        screen.next_snapshot()
        alice.post(reg_url(other))  # чужое событие — снимка быть не должно
        alice.post(reg_url(ev))
        # Следующий снимок — уже про своё событие, промежуточного нет.
        assert screen.next_snapshot()["counts"]["confirmed"] == 1
    finally:
        screen.close()


def test_two_open_screens_both_update(server, client, make_client):
    """G5: два открытых экрана организатора получают одно и то же изменение."""
    register(client, "org@example.com")
    ev = make_event(client)
    screens = [Stream(server, token(client), ev) for _ in range(2)]
    try:
        for s in screens:
            s.next_snapshot()
        participant(make_client, "alice@example.com").post(reg_url(ev))
        assert [s.next_snapshot()["counts"]["confirmed"] for s in screens] == [1, 1]
    finally:
        for s in screens:
            s.close()


def test_reconnect_gets_current_state(server, client, make_client):
    """5.6: пока поток был закрыт, состав изменился — после переподключения он виден сразу."""
    register(client, "org@example.com")
    ev = make_event(client)
    screen = Stream(server, token(client), ev)
    screen.next_snapshot()
    screen.close()

    participant(make_client, "alice@example.com").post(reg_url(ev))

    screen = Stream(server, token(client), ev)
    try:
        assert screen.next_snapshot()["counts"]["confirmed"] == 1
    finally:
        screen.close()


def test_closed_tab_releases_listen_connection(server, client):
    """Закрытая вкладка не оставляет висящее соединение LISTEN в БД."""

    def listeners():
        with engine.connect() as conn:
            return conn.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE query ILIKE 'LISTEN%' AND pid <> pg_backend_pid()"
                )
            ).scalar()

    register(client, "org@example.com")
    ev = make_event(client)
    before = listeners()
    screen = Stream(server, token(client), ev)
    screen.next_snapshot()
    assert listeners() == before + 1
    screen.close()

    deadline = time.monotonic() + 5
    while listeners() != before and time.monotonic() < deadline:
        time.sleep(0.1)
    assert listeners() == before


def test_live_stream_access(client, make_client):
    """F8: поток доступен только организатору события."""
    register(client, "org@example.com")
    ev = make_event(client)
    other = participant(make_client, "other@example.com")
    url = f"/api/events/{ev}/attendees/live"
    assert make_client().get(url).status_code == 401
    assert other.get(url).status_code == 403
    assert client.get("/api/events/999/attendees/live").status_code == 404


def test_session_cookie_hidden_from_docs(client):
    """Поле ep_session больше не показывается в Swagger: cookie передаёт браузер."""
    assert "ep_session" not in json.dumps(client.get("/openapi.json").json())
