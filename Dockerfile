FROM python:3.11-slim AS develop

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && apt-get install -y ffmpeg nvtop vim libc++1 libc++abi1 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen

COPY . .

RUN uv run python -c "import torch; torch.hub.load('snakers4/silero-vad', 'silero_vad', trust_repo=True)"

ENV PYTHONPATH=/app/src

CMD ["uv", "run", "python", "-m", "src.api.main"]
