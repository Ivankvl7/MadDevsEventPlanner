from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import get_db
from app.main import app


def test_health_ok_when_database_available():
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_503_when_database_unavailable():
    # Порт 1 заведомо закрыт: имитируем недоступную БД.
    broken = create_engine(
        "postgresql+psycopg://nobody:nobody@127.0.0.1:1/none",
        connect_args={"connect_timeout": 1},
    )
    broken_session = sessionmaker(bind=broken)

    def override():
        with broken_session() as s:
            yield s

    app.dependency_overrides[get_db] = override
    try:
        response = TestClient(app).get("/api/health")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503
    assert response.json() == {"status": "error", "database": "unavailable"}
