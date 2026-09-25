#!/usr/bin/env bash
# Wait until MySQL accepts connections.
set -e

HOST="${DB_HOST:-mysql}"
PORT="${DB_PORT:-3306}"
USER="${DB_USER:-imageurl}"
PASSWORD="${DB_PASSWORD:-imageurl_pwd}"

echo "[wait-for-mysql] waiting for $HOST:$PORT ..."
for i in $(seq 1 60); do
  if python -c "
import socket, sys
s = socket.socket()
s.settimeout(2)
try:
    s.connect(('$HOST', $PORT))
    s.close()
except Exception as e:
    sys.exit(1)
sys.exit(0)
" >/dev/null 2>&1; then
    echo "[wait-for-mysql] TCP up"
    break
  fi
  sleep 1
done

# Try a real SELECT 1 to be sure the server is accepting queries
echo "[wait-for-mysql] waiting for SELECT 1 ..."
for i in $(seq 1 30); do
  if python - <<PY
import os, pymysql
try:
    c = pymysql.connect(host='$HOST', port=$PORT, user='$USER', password='$PASSWORD', connect_timeout=3)
    cur = c.cursor()
    cur.execute("SELECT 1")
    cur.close(); c.close()
except Exception:
    raise SystemExit(1)
PY
  then
    echo "[wait-for-mysql] MySQL is ready"
    exit 0
  fi
  sleep 2
done

echo "[wait-for-mysql] MySQL not ready after 60s"
exit 1