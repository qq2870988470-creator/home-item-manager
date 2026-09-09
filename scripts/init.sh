#!/usr/bin/env bash
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/env.sh"
mkdir -p "$STORAGE_ROOT/images" "$DATA_ROOT/postgres" "$DATA_ROOT/redis" "$BACKUP_ROOT"
chmod 700 "$BACKUP_ROOT"
chmod 600 .env
"${DC[@]}" build
# Only initialize ownership of EMPTY directories. Never recursively alter existing NAS data/ACLs.
for service in postgres redis backend; do
  case "$service" in
    postgres) directory=/var/lib/postgresql/data; owner=postgres; mode=700;;
    redis) directory=/data; owner=redis; mode=755;;
    backend) directory=/app/storage/images; owner=10001:10001; mode=755;;
  esac
  "${DC[@]}" run --rm -T --no-deps --user 0 --entrypoint sh "$service" -c '
    if [ -z "$(ls -A "$1")" ]; then chown "$2" "$1" && chmod "$3" "$1";
    else echo "已有数据：保留 $1 的权限，由部署检查验证。"; fi
  ' sh "$directory" "$owner" "$mode"
done
bash "$ROOT/scripts/check-deployment.sh"
echo '初始化完成。执行 docker compose up -d --build --wait'
