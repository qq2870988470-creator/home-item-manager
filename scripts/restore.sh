#!/usr/bin/env bash
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
[ "$#" = 1 ] || { echo '用法：bash scripts/restore.sh data/backups/时间目录'; exit 1; }
BACKUP="$(cd "$1" && pwd)"
[ -f "$BACKUP/manifest.txt" ] || { echo '缺少备份清单'; exit 1; }
(cd "$BACKUP" && checksum -c SHA256SUMS)
"${DC[@]}" exec -T postgres pg_restore --list < "$BACKUP/database.dump" >/dev/null
"${DC[@]}" run --rm -T --no-deps backend python -m app.image_archive validate < "$BACKUP/images.tar.gz"
echo "将覆盖当前数据库。来源：$BACKUP"
echo '恢复前会自动备份当前数据库和图片。仅恢复可信的本项目备份。'
read -r -p '输入 RESTORE 确认：' confirmation
[ "$confirmation" = RESTORE ] || { echo '已取消'; exit 1; }
stop_writes
make_backup
# Restore files first. If interrupted, the old DB still has all of its files.
# Files are UUID-named and immutable; unrelated originals are deliberately retained.
"${DC[@]}" run --rm -T --no-deps --user 0 backend python -m app.image_archive restore < "$BACKUP/images.tar.gz"
"${DC[@]}" exec -T postgres sh -c 'exec pg_restore --clean --if-exists --single-transaction --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$BACKUP/database.dump"
# Old cache versions can collide with restored database versions. Flush only this dedicated Redis DB.
"${DC[@]}" exec -T redis sh -c 'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli -e FLUSHDB | grep -qx OK' || { RESTART=0; echo '缓存清理失败：后端保持停止，修复 Redis 并 FLUSHDB 后再启动后端。'; exit 1; }
"${DC[@]}" run --rm -T --no-deps backend alembic upgrade head || { RESTART=0; echo '迁移失败，后端保持停止，请检查迁移和备份。'; exit 1; }
echo "恢复完成。恢复前快照：$LAST_BACKUP"
