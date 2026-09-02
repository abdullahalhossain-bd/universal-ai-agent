# Universal AI Agent

FastAPI service for AI-powered ecommerce chat: product search, website
knowledge (RAG), stock lookup, and merchant catalog sync.

## Running locally with Docker

Prerequisites: Docker + Docker Compose.

```bash
cp .env.example .env
# fill in at least CREDENTIAL_ENCRYPTION_KEY and one GROQ_API_KEY_n
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

docker compose up --build
```

This starts:

| service    | what                                                        |
|------------|--------------------------------------------------------------|
| `postgres` | Postgres 16 + pgvector (`pgvector/pgvector:pg16`)             |
| `redis`    | queue backing the sync worker + rate limiting                 |
| `api`      | the FastAPI app on `http://localhost:8000` (`/health`, `/docs`) |
| `worker`   | `app.sync.worker` — drains the catalog-sync job queue          |

The `api` container's entrypoint (`docker/entrypoint.sh`) waits for
Postgres to accept connections, then runs `alembic upgrade head`
before starting uvicorn — schema is always current for the image
being deployed, no manual migration step. The `worker` container
shares the same entrypoint but skips migrations
(`SKIP_MIGRATIONS=1`) so two containers don't race the same
`alembic upgrade` on cold start.

Tear down (keeping data): `docker compose down`.
Tear down and wipe the database volume: `docker compose down -v`.

## Running without Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

cp .env.example .env   # point DATABASE_URL/REDIS_URL at services you run yourself
alembic upgrade head
uvicorn app.main:app --reload
```

## Tests

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -v
```

The suite runs entirely against sqlite / mocked settings (see
`tests/conftest.py`) — no live Postgres or Redis required, except
`tests/test_migrations.py`'s Postgres-parity checks, which also run
against a throwaway sqlite DB.

## CI

`.github/workflows/ci.yml` runs on every push/PR to `main`:

- **test** — installs `requirements.txt` + `requirements-dev.txt`, runs `pytest`.
- **docker-build** — builds the image (no push) so a broken
  `Dockerfile` or missing runtime dependency fails CI, not a
  deployment.
- **migrations** — spins up a real `pgvector/pgvector:pg16` service
  container and runs `alembic upgrade head` against it, catching
  anything sqlite's migration test can't (e.g. Postgres-only DDL like
  `CREATE EXTENSION vector`).

Image publishing (push to a registry) is stubbed out but commented in
the workflow — enable it deliberately once you have somewhere to push
to and a release trigger you're happy with.

## Environment variables

See `.env.example` for the full list. `DATABASE_URL` and
`CREDENTIAL_ENCRYPTION_KEY` are required; everything else has a
sane default for local dev.
