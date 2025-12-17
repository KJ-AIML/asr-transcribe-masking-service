FROM python:3.11-slim AS develop

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && apt-get install -y ffmpeg

WORKDIR /app

COPY . .

RUN uv sync --frozen --no-cache

ENV PYTHONPATH=/app/src

CMD ["uv", "run", "python", "-m", "src.api.main"]