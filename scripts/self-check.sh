#!/usr/bin/env bash
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
# This deliberately restarts services. Run during maintenance; test records are retained.
bash "$ROOT/scripts/check-deployment.sh"
"${DC[@]}" up -d --build --wait --wait-timeout 180
read -r ITEM_ID PHOTO_URL PHOTO_SHA <<< "$("${DC[@]}" exec -T backend python - create < scripts/acceptance_api.py)"
[[ "$ITEM_ID" =~ ^[0-9]+$ ]] || fail '未获得测试物品 ID。'
verify() { "${DC[@]}" exec -T backend python - verify "$ITEM_ID" "$PHOTO_URL" "$PHOTO_SHA" < scripts/acceptance_api.py; }
verify
"${DC[@]}" stop backend
"${DC[@]}" rm -f backend
"${DC[@]}" up -d --wait backend
# Allow Docker DNS proxy cache to expire; bounded retries, not unbounded sleeps.
for attempt in {1..15}; do if verify; then break; fi; sleep 1; done
verify
"${DC[@]}" up -d --force-recreate --wait frontend
verify
"${DC[@]}" restart postgres
"${DC[@]}" up -d --wait postgres
verify
"${DC[@]}" up -d --force-recreate --wait postgres
verify
"${DC[@]}" exec -T redis sh -c 'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli SET selfcheck:aof persisted EX 600'
"${DC[@]}" up -d --force-recreate --wait redis
[ "$("${DC[@]}" exec -T redis sh -c 'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli GET selfcheck:aof')" = persisted ] || fail 'Redis AOF 重建验证失败。'
stop_writes
make_backup
"${DC[@]}" start backend
RESTART=0
# Restore into an isolated temporary PostgreSQL container. Never overwrite the app database.
CHECK_CONTAINER="him-restore-check-$$"
selfcheck_cleanup() {
  result=$?
  trap - EXIT
  docker rm -f "$CHECK_CONTAINER" >/dev/null 2>&1 || true
  if [ "$RESTART" = 1 ]; then "${DC[@]}" start backend || result=1; fi
  rmdir "$LOCK" || true
  exit "$result"
}
trap selfcheck_cleanup EXIT
DB_USER="$(env_value POSTGRES_USER)"
DB_NAME="$(env_value POSTGRES_DB)"
docker run -d --name "$CHECK_CONTAINER" --network none --tmpfs /var/lib/postgresql/data \
  -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_USER="$DB_USER" -e POSTGRES_DB="$DB_NAME" postgres:17-alpine >/dev/null
for attempt in {1..60}; do
  if docker exec "$CHECK_CONTAINER" pg_isready -h 127.0.0.1 -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; then break; fi
  sleep 1
done
docker exec -i "$CHECK_CONTAINER" pg_restore --exit-on-error --no-owner --no-privileges -U "$DB_USER" -d "$DB_NAME" < "$LAST_BACKUP/database.dump"
[ "$(docker exec "$CHECK_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -Atc "SELECT count(*) FROM items WHERE id=$ITEM_ID")" = 1 ] || fail '恢复后的数据库缺少测试物品。'
[ "$(docker exec "$CHECK_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -Atc "SELECT count(*) FROM item_location_history WHERE item_id=$ITEM_ID")" = 2 ] || fail '恢复后历史记录不完整。'
# Override image directory with a temporary container directory; verify restored bytes.
"${DC[@]}" run --rm -T --no-deps --user 0 -e IMAGE_DIR=/tmp/restored-images backend sh -c '
  python -m app.image_archive restore && python -c "import hashlib,pathlib,sys; assert hashlib.sha256((pathlib.Path(\"/tmp/restored-images\")/sys.argv[1]).read_bytes()).hexdigest()==sys.argv[2]" "$1" "$2"
' sh "${PHOTO_URL##*/}" "$PHOTO_SHA" < "$LAST_BACKUP/images.tar.gz"
echo "自检通过。测试物品 ID=$ITEM_ID；备份=$LAST_BACKUP。隔离恢复已验证，正式库未被覆盖。"
