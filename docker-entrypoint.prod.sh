#!/bin/sh
set -eu

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    python manage.py migrate --noinput
fi

if [ "${COLLECT_STATIC:-1}" = "1" ]; then
    python manage.py collectstatic --noinput --clear
fi

python manage.py check --deploy
exec "$@"
