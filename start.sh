#!/usr/bin/env sh
set -eu

PORT_VALUE="${PORT:-8080}"
DATABASE_SET="${DATABASE_URL:+yes}"
DATABASE_SET="${DATABASE_SET:-no}"

echo "PORT=${PORT_VALUE}"
echo "DATABASE_URL set? ${DATABASE_SET}"
python -V
alembic --version || true

if [ "${SKIP_MIGRATIONS:-0}" = "1" ]; then
  echo "SKIP_MIGRATIONS=1, skipping alembic upgrade head"
else
  echo "Waiting for database connectivity before migrations..."
  python - <<'PY'
import os
import time
from sqlalchemy import create_engine, text

url = os.environ.get("DATABASE_URL")
assert url, "DATABASE_URL missing"

engine_kwargs = {"pool_pre_ping": True}
if url.startswith("postgresql"):
    engine_kwargs["connect_args"] = {"connect_timeout": 2}

for i in range(30):
    try:
        engine = create_engine(url, **engine_kwargs)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("DB ready", flush=True)
        break
    except Exception as ex:
        print(f"DB not ready ({i + 1}/30): {ex}", flush=True)
        time.sleep(2)
else:
    raise SystemExit("DB never became ready")
PY

  echo "Running alembic migrations..."
  migration_attempt=1
  migration_max_attempts=5
  while true; do
    echo "alembic upgrade head (attempt ${migration_attempt}/${migration_max_attempts})"
    if alembic upgrade head; then
      echo "Migrations completed"
      break
    fi

    if [ "${migration_attempt}" -ge "${migration_max_attempts}" ]; then
      echo "Migration failed after ${migration_max_attempts} attempts"
      exit 1
    fi

    migration_attempt=$((migration_attempt + 1))
    echo "Migration attempt failed, retrying in 2 seconds..."
    sleep 2
  done
fi

echo "Starting uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT_VALUE}"
