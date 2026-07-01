FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Omit development dependencies
ENV UV_NO_DEV=1
ENV UV_PYTHON_DOWNLOADS=0

WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    glib2.0 \
    libgomp1 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 999 odometer \
 && useradd --system --gid 999 --uid 999 --create-home odometer

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

USER odometer

WORKDIR /app

EXPOSE 8000

CMD ["uv", "run", "--with", "opencv-contrib-python-headless", "--with", "paddleocr", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
