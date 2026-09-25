#!/usr/bin/env bash
# Entrypoint for api container:
#   wait-for-mysql -> alembic upgrade -> optional seed -> uvicorn
set -e

cd /code

bash /code/scripts/wait-for-mysql.sh

echo "[entrypoint] running alembic upgrade head ..."
alembic upgrade head

# Seed runs every time; app/seed.py is idempotent (uses ON DUPLICATE KEY / SELECT-then-INSERT).
echo "[entrypoint] running seed ..."
python -m app.seed

echo "[entrypoint] starting: $*"
exec "$@"