#!/usr/bin/env bash
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/env.sh"
for key in APP_ENV POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD REDIS_HOST REDIS_PORT REDIS_PASSWORD; do
  value="$(env_value "$key")"
  [ -n "$value" ] || fail "缺少必需环境变量：$key"
  case "$key:$value" in
    POSTGRES_PASSWORD:change_me*|REDIS_PASSWORD:change_me*|*PASSWORD:replace_with*) fail "$key 仍为示例密码；请生成独立的长随机密码。";;
  esac
done
mkdir -p "$DATA_ROOT/postgres" "$DATA_ROOT/redis" "$STORAGE_ROOT/images" "$BACKUP_ROOT" || fail '无法创建数据目录；请在 fnOS 共享目录权限中授权部署账号。'
probe="$BACKUP_ROOT/.write-check-$$"
(umask 077; : > "$probe") || fail "备份目录不可写：$BACKUP_ROOT"
rm -- "$probe"
# Check as real container service users, because host and container UIDs differ.
# No chmod or chown is performed by this checking script.
for service in postgres redis backend; do
  case "$service" in
    postgres) directory=/var/lib/postgresql/data; owner=postgres; host_path="$DATA_ROOT/postgres";;
    redis) directory=/data; owner=redis; host_path="$DATA_ROOT/redis";;
    backend) directory=/app/storage/images; owner=10001:10001; host_path="$STORAGE_ROOT/images";;
  esac
  "${DC[@]}" run --rm -T --no-deps --user "$owner" --entrypoint sh "$service" -c '
    probe="$1/.write-check-$$"
    (umask 077; : > "$probe") && rm -- "$probe"
  ' sh "$directory" || fail "$service 无法写入 $host_path（或镜像尚未构建）。首次空目录请运行 bash scripts/init.sh；已有数据请在 NAS 上检查属主/ACL，禁止 chmod 777。"
done
"${DC[@]}" run --rm -T --no-deps --user postgres --entrypoint sh postgres -c '
  if [ -f /var/lib/postgresql/data/PG_VERSION ]; then
    actual=$(cat /var/lib/postgresql/data/PG_VERSION)
    [ "$actual" = 17 ] || { echo "数据目录属于 PostgreSQL $actual，本项目要求 17，禁止直接跨主版本启动。" >&2; exit 1; }
  fi
' || fail 'PostgreSQL 目录版本检查失败；请先制定逻辑备份恢复迁移方案。'
echo "检查通过。CPU 架构：$(docker info --format '{{.Architecture}}')"
echo "PostgreSQL 17：$DATA_ROOT/postgres"
echo "Redis AOF：$DATA_ROOT/redis"
echo "图片：$STORAGE_ROOT/images"
echo "备份：$BACKUP_ROOT（后端只读挂载 /app/backups）"
