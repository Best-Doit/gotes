#!/bin/bash
set -eu
cd "$(dirname "$0")/../.."
AUDIT_NET="gotes-audit-$(date +%s)-$$"
AUDIT_DB="$AUDIT_NET-db"
cleanup() {
  docker rm -f -v "$AUDIT_DB" >/dev/null 2>&1 || true
  docker network rm "$AUDIT_NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT
docker network create --internal "$AUDIT_NET" >/dev/null
docker run -d --name "$AUDIT_DB" --network "$AUDIT_NET" -e POSTGRES_PASSWORD=audit-only-password -e POSTGRES_USER=audit -e POSTGRES_DB=audit postgres:16-alpine >/dev/null
for attempt in {1..30}; do
  if docker exec "$AUDIT_DB" pg_isready -U audit -d audit >/dev/null 2>&1; then break; fi
  sleep 1
done
docker run --rm --network "$AUDIT_NET" --entrypoint python -v "$PWD:/app:ro" -e POSTGRES_HOST="$AUDIT_DB" -e POSTGRES_DB=audit -e POSTGRES_USER=audit -e POSTGRES_PASSWORD=audit-only-password -e GOTES_DATA_DIR=/tmp/gotes-audit -e GOTES_MEDIA_ROOT=/tmp/gotes-audit-media -e DJANGO_DEBUG=1 gotes-web:latest manage.py test --noinput
