#!/usr/bin/env bash
# Read Compose's dotenv interpretation; never source .env as executable shell code.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
fail() { echo "错误：$*" >&2; exit 1; }
command -v docker >/dev/null || fail '未安装 Docker。Mac 安装 Docker Desktop；fnOS 启用 Docker。'
docker compose version >/dev/null 2>&1 || fail 'Docker Compose v2 不可用。'
docker info >/dev/null 2>&1 || fail 'Docker 服务未启动，或当前账号无权访问 Docker。'
[ -f .env ] || fail '缺少 .env；复制 .env.example 并修改密码和数据路径。'
DC=(docker compose --project-directory "$ROOT" --env-file "$ROOT/.env" -f "$ROOT/docker-compose.yml")
"${DC[@]}" config --quiet || fail 'Docker Compose 配置不合法或必需变量缺失。'
COMPOSE_ENV="$("${DC[@]}" config --environment)"
env_value() { printf '%s\n' "$COMPOSE_ENV" | sed -n "s/^$1=//p"; }
DATA_ROOT="$(env_value DATA_ROOT)"; DATA_ROOT="${DATA_ROOT:-./data}"
STORAGE_ROOT="$(env_value STORAGE_ROOT)"; STORAGE_ROOT="${STORAGE_ROOT:-./storage}"
case "$DATA_ROOT" in /*) ;; *) DATA_ROOT="$ROOT/$DATA_ROOT";; esac
case "$STORAGE_ROOT" in /*) ;; *) STORAGE_ROOT="$ROOT/$STORAGE_ROOT";; esac
[ "$DATA_ROOT" != / ] && [ "$STORAGE_ROOT" != / ] || fail '数据根目录不能是 /。'
BACKUP_ROOT="$DATA_ROOT/backups"
checksum() {
  if command -v sha256sum >/dev/null; then sha256sum "$@";
  elif command -v shasum >/dev/null; then shasum -a 256 "$@";
  else fail '缺少 sha256sum 或 shasum，请安装校验工具。'; fi
}
