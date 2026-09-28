#!/bin/sh
set -eu

# Fail before changing the database if production security settings are invalid.
python manage.py check_production_security

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    python manage.py migrate --noinput
fi

if [ "${COLLECT_STATIC:-1}" = "1" ]; then
    python manage.py collectstatic --noinput --clear
fi

exec "$@"
