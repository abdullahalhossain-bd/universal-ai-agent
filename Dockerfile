# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Builder: compile wheels for anything needing a C toolchain
# (psycopg2-binary ships wheels, but sentence-transformers/torch and
# rapidfuzz pull in packages that sometimes need build headers on
# slim images — keeping the toolchain confined to this stage keeps
# the final image small).
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Embeddings run on CPU in the API/worker image. Install the CPU wheel
# first so sentence-transformers does not resolve a multi-gigabyte CUDA
# runtime into the production image.
RUN pip install --no-cache-dir --prefix=/install \
        --index-url https://download.pytorch.org/whl/cpu \
        "torch>=2.0,<3.0" \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------------------------------------------------------------------------
# Runtime: slim image, no compilers, non-root user
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# libpq5 is the psycopg2 runtime dependency (libpq-dev's headers are
# not needed here, only the shared library).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app \
    && useradd --system --gid app --home /app --shell /usr/sbin/nologin app

COPY --from=builder /install /usr/local

WORKDIR /app

COPY --chown=app:app . .

# Container-local dirs the app/alembic may write to (e.g. HF cache
# for sentence-transformers on first embedding call).
RUN mkdir -p /app/.cache && chown -R app:app /app

USER app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/app/.cache \
    PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/ready" || exit 1

# `entrypoint.sh` runs migrations (`alembic upgrade head`) before
# handing off to uvicorn — see that file for why this is safe to run
# on every container start, including scaled-out replicas.
ENTRYPOINT ["/app/docker/entrypoint.sh"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
