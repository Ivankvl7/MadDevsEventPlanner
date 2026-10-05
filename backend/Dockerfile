FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Сначала только зависимости — слой кэшируется, пока не меняется lock-файл.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
