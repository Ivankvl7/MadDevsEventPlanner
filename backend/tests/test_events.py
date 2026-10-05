from tests.conftest import future, register


def event_payload(**overrides):
    data = {
        "title": "Митап",
        "description": "Описание",
        "starts_at": future(48),
        "timezone": "Asia/Bishkek",
        "capacity": 10,
    }
    data.update(overrides)
    return data


def test_create_requires_login(client):
    assert client.post("/api/events", json=event_payload()).status_code == 401


def test_create_and_read_event(client, make_client, frozen_clock):
    register(client, "org@example.com", name="Организатор")
    r = client.post("/api/events", json=event_payload(starts_at="2030-01-12T15:00:00+06:00"))
    assert r.status_code == 201, r.text
    ev = r.json()
    assert ev["title"] == "Митап"
    assert ev["capacity"] == 10
    assert ev["timezone"] == "Asia/Bishkek"
    assert ev["organizer"]["name"] == "Организатор"
    # Момент сохраняется точно; ответ — в UTC.
    assert ev["starts_at"].startswith("2030-01-12T09:00:00")

    anon = make_client()
    assert anon.get(f"/api/events/{ev['id']}").json() == ev
    assert [e["id"] for e in anon.get("/api/events").json()] == [ev["id"]]


def test_event_validation(client, frozen_clock):
    register(client, "org@example.com")
    cases = [
        event_payload(capacity=0),
        event_payload(title="   "),
        event_payload(timezone="Mars/Olympus"),
        event_payload(starts_at="2030-01-12T15:00:00"),  # без часового пояса
    ]
    for payload in cases:
        assert client.post("/api/events", json=payload).status_code == 422, payload
    past = client.post("/api/events", json=event_payload(starts_at=future(-1)))
    assert past.status_code == 422
    assert past.json()["detail"] == "Дата события уже прошла"


def test_only_organizer_can_edit(client, make_client, frozen_clock):
    register(client, "org@example.com")
    ev = client.post("/api/events", json=event_payload()).json()

    other = make_client()
    register(other, "other@example.com")
    assert other.patch(f"/api/events/{ev['id']}", json={"title": "X"}).status_code == 403
    assert make_client().patch(f"/api/events/{ev['id']}", json={"title": "X"}).status_code == 401

    r = client.patch(f"/api/events/{ev['id']}", json={"title": "Новое", "capacity": 20})
    assert r.status_code == 200
    assert (r.json()["title"], r.json()["capacity"]) == ("Новое", 20)


def test_reschedule_rules(client, frozen_clock):
    register(client, "org@example.com")
    ev = client.post("/api/events", json=event_payload(starts_at=future(48))).json()
    url = f"/api/events/{ev['id']}"

    assert client.patch(url, json={"starts_at": future(-1)}).status_code == 422
    ok = client.patch(url, json={"starts_at": future(72)})
    assert ok.status_code == 200

    frozen_clock.advance(hours=73)  # событие началось
    started = client.patch(url, json={"starts_at": future(24)})
    assert started.status_code == 409
    # Описание после начала менять можно.
    assert client.patch(url, json={"description": "Итоги"}).status_code == 200


def test_missing_event_404(client):
    assert client.get("/api/events/999").status_code == 404
