#!/usr/bin/env bash
#
# Runs before every container start (web AND worker use this same
# image/entrypoint). Two responsibilities:
#
#   1. Wait for Postgres to actually accept connections — `depends_on`
#      in docker-compose only waits for the container to start, not
#      for Postgres inside it to finish initializing.
#   2. Run `alembic upgrade head` so the schema is always in sync
#      with the image being deployed — no separate manual migration
#      step to forget.
#
# Running migrations from every replica on every start is safe here:
# Alembic's own `alembic_version` table plus Postgres row locking
# during DDL make concurrent `upgrade head` calls converge rather
# than corrupt each other. For high-replica-count deployments, prefer
# running migrations as a separate one-off Job/step in CI instead and
# set SKIP_MIGRATIONS=1 here.

set -euo pipefail

python - <<'PYEOF'
import sys
import time

from sqlalchemy import create_engine, text

from app.core.config import settings

deadline = time.monotonic() + 60
last_error = None

while time.monotonic() < deadline:
    try:
        engine = create_engine(settings.database_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("database is ready", flush=True)
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        last_error = exc
        print(f"database not ready yet ({exc}); retrying...", flush=True)
        time.sleep(2)

print(f"database never became ready: {last_error}", file=sys.stderr)
sys.exit(1)
PYEOF

if [ "${SKIP_MIGRATIONS:-0}" != "1" ]; then
    echo "running alembic upgrade head..."
    alembic upgrade head
fi

exec "$@"
