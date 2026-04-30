#!/usr/bin/env bash
# Migrate PostgreSQL from Render (expires 90 days) to Neon (free forever)
#
# Prerequisites:
#   - pg_dump / psql installed (apt install postgresql-client)
#   - Render DATABASE_URL (source)
#   - Neon DATABASE_URL (destination) — get from neon.tech free tier
#
# Usage:
#   SOURCE_DB="postgresql://orquanta:PWD@dpg-xxx-a/orquanta_pw23" \
#   TARGET_DB="postgresql://orquanta:PWD@ep-xxx.us-east-2.aws.neon.tech/orquanta?sslmode=require" \
#   bash infra/migrate-db.sh

set -euo pipefail

SOURCE_DB="${SOURCE_DB:?Set SOURCE_DB (Render connection string)}"
TARGET_DB="${TARGET_DB:?Set TARGET_DB (Neon connection string)}"
DUMP_FILE="/tmp/orquanta-$(date +%Y%m%d-%H%M%S).sql"

echo "==> Dumping Render PostgreSQL → $DUMP_FILE ..."
pg_dump \
  --no-owner \
  --no-acl \
  --clean \
  --if-exists \
  --format=plain \
  "$SOURCE_DB" > "$DUMP_FILE"

ROWS=$(grep -c "^INSERT INTO\|^COPY " "$DUMP_FILE" 2>/dev/null || echo "0")
echo "    Dump complete — ~$ROWS data statements, $(du -sh "$DUMP_FILE" | cut -f1) on disk"

echo ""
echo "==> Restoring to Neon PostgreSQL..."
psql "$TARGET_DB" < "$DUMP_FILE"

echo ""
echo "==> Verifying row counts..."
psql "$TARGET_DB" -c "SELECT COUNT(*) AS users FROM users;" 2>/dev/null || true

echo ""
echo "Done! Update DATABASE_URL in Render dashboard → Environment Variables:"
echo "  DATABASE_URL = $TARGET_DB"
echo ""
echo "Then redeploy the Render service to pick up the new DB."
