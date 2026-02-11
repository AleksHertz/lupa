#!/usr/bin/env sh
set -eu

PORT_VALUE="${PORT:-8080}"
DATABASE_SET="${DATABASE_URL:+yes}"
DATABASE_SET="${DATABASE_SET:-no}"

echo "PORT=${PORT_VALUE}"
echo "DATABASE_URL set? ${DATABASE_SET}"
python -V
alembic --version || true

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  echo "RUN_MIGRATIONS=1 -> running alembic upgrade head"
  alembic upgrade head
  echo "Migrations completed"
else
  echo "RUN_MIGRATIONS!=1 -> skipping migrations"
fi

echo "Starting uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT_VALUE}"
