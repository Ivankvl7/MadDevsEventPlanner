# EventPlanner — регистрация на мероприятия

Тестовое задание №9. Документы: [критерии приёмки](docs/acceptance.md), [выбор стека](docs/stack.md), [журнал разработки](docs/development-log.md).

> Статус: этап 0 — каркас. Есть backend с проверкой здоровья (`/api/health`), frontend, показывающий статус backend, и docker-compose. Функциональности задания пока нет. Полное описание состояния будет в конце работы.

## Запуск через Docker

Нужен Docker Desktop (Docker Compose v2).

```bash
cp .env.example .env        # необязательно: значения по умолчанию подходят для локального запуска
docker compose up --build
```

- Frontend: http://localhost:8080
- Backend API и Swagger UI: http://localhost:8000/docs
- PostgreSQL: `localhost:5433` (не 5432, чтобы не конфликтовать с локально установленной PostgreSQL)

## Разработка без Docker для приложения

Нужны Python 3.14 + [uv](https://docs.astral.sh/uv/), Node.js 20.19+ / 22.12+. База — из compose: `docker compose up -d db`.

```bash
# backend (http://localhost:8000)
cd backend
uv sync
uv run uvicorn app.main:app --reload

# frontend (http://localhost:5173, /api проксируется на backend)
cd frontend
npm install
npm run dev
```

## Тесты

Тесты backend идут на настоящей PostgreSQL; тестовая база `eventplanner_test` создаётся автоматически.

```bash
docker compose up -d db
cd backend
uv run pytest
```

Другой адрес базы задаётся переменной `TEST_DATABASE_URL`.
