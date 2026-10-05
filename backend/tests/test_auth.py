from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import func, select

from app import models
from app.db import SessionLocal
from tests.conftest import register


def test_register_login_me_logout(client):
    user = register(client, "  Alice@Example.COM ", name="Алиса")
    assert user["email"] == "alice@example.com"  # нормализация
    assert client.get("/api/auth/me").json()["name"] == "Алиса"

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401

    r = client.post(
        "/api/auth/login", json={"email": "ALICE@example.com", "password": "password123"}
    )
    assert r.status_code == 200
    assert client.get("/api/auth/me").json()["email"] == "alice@example.com"


def test_session_cookie_is_httponly(client):
    r = client.post(
        "/api/auth/register",
        json={"email": "a@example.com", "password": "password123", "name": "A"},
    )
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


def test_password_is_hashed(client):
    register(client, "a@example.com", password="secret-pass-1")
    with SessionLocal() as db:
        stored = db.scalar(select(models.User.password_hash))
    assert "secret-pass-1" not in stored
    assert stored.startswith("scrypt$")


def test_wrong_password_and_unknown_user(client):
    register(client, "a@example.com")
    client.post("/api/auth/logout")
    bad = client.post("/api/auth/login", json={"email": "a@example.com", "password": "wrong-pass"})
    unknown = client.post(
        "/api/auth/login", json={"email": "b@example.com", "password": "password123"}
    )
    assert bad.status_code == unknown.status_code == 401
    assert bad.json() == unknown.json()  # не раскрываем, существует ли email


def test_duplicate_email_rejected(client, make_client):
    register(client, "a@example.com")
    r = make_client().post(
        "/api/auth/register",
        json={"email": "A@EXAMPLE.com", "password": "password123", "name": "B"},
    )
    assert r.status_code == 409


def test_concurrent_duplicate_registration_creates_one_user(make_client):
    clients = [make_client() for _ in range(8)]

    def attempt(c):
        return c.post(
            "/api/auth/register",
            json={"email": "race@example.com", "password": "password123", "name": "R"},
        ).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(attempt, clients))
    assert sorted(codes) == [201] + [409] * 7
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(models.User)) == 1


def test_validation(client):
    r = client.post(
        "/api/auth/register", json={"email": "not-an-email", "password": "short", "name": ""}
    )
    assert r.status_code == 422
    fields = {e["loc"][-1] for e in r.json()["detail"]}
    assert fields == {"email", "password", "name"}
