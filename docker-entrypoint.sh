#!/bin/sh
set -e

wait_for_db() {
  python - <<'PY'
import os
import time
import psycopg2

host = os.getenv("DB_HOST", "db")
port = int(os.getenv("DB_PORT", "5432"))
name = os.getenv("DB_NAME", "lineops")
user = os.getenv("DB_USER", "lineops")
password = os.getenv("DB_PASSWORD", "")

for attempt in range(1, 31):
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=name,
            user=user,
            password=password,
            connect_timeout=3,
        )
        conn.close()
        print("Database is ready")
        break
    except Exception:
        if attempt == 30:
            raise
        print(f"Waiting for database... attempt {attempt}/30")
        time.sleep(2)
PY
}

if [ "${WAIT_FOR_DB:-1}" = "1" ]; then
  wait_for_db
fi

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  python manage.py migrate --noinput
fi

if [ "${COLLECT_STATIC:-1}" = "1" ]; then
  python manage.py collectstatic --noinput
fi

exec "$@"
