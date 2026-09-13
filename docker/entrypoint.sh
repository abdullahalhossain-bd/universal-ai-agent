#!/usr/bin/env bash
set -euo pipefail

# Prefer discrete DB settings in container deployments. This avoids breaking
# DATABASE_URL when a password contains @, :, /, #, %, spaces, etc.
if [[ -n "${DB_HOST:-}" ]]; then
    export DATABASE_URL="$(python - <<'PYEOF'
import os
from urllib.parse import quote_plus
scheme = os.getenv("DB_SCHEME", "postgresql")
user = quote_plus(os.environ["DB_USER"])
password = quote_plus(os.environ["DB_PASSWORD"])
host = os.environ["DB_HOST"]
port = os.getenv("DB_PORT", "5432")
db = os.environ["DB_NAME"]
print(f"{scheme}://{user}:{password}@{host}:{port}/{db}")
PYEOF
)"
fi

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
    except Exception as exc:
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

# One-time-safe production migration for legacy plaintext datasource URLs.
# The script is idempotent and skips rows already encrypted with enc$v1$.
# Keep this on the API service only via RUN_CREDENTIAL_BACKFILL=1 so worker
# startup cannot race the migration.
if [ "${RUN_CREDENTIAL_BACKFILL:-0}" = "1" ]; then
    echo "running datasource credential backfill..."
    python -m scripts.encrypt_legacy_connection_urls --apply
fi

exec "$@"
