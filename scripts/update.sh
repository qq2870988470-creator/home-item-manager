#!/usr/bin/env bash
# Execute in a subshell so git pull cannot change the currently interpreted program.
(
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
command -v git >/dev/null || fail '未安装 Git。'
git rev-parse --is-inside-work-tree >/dev/null || fail '当前项目不是 Git 仓库。'
[ -z "$(git status --porcelain)" ] || fail '工作区有未提交修改，请先提交或处理；不会自动覆盖本地文件。'
OLD_COMMIT="$(git rev-parse HEAD)"
PHASE=backup
failure() {
  echo "更新失败，阶段：$PHASE；原版本：$OLD_COMMIT" >&2
  echo "更新前备份：${LAST_BACKUP:-尚未完成}" >&2
  echo '不要删除数据目录。查看 docker compose logs --tail=100；迁移后不自动回滚代码或数据库。' >&2
  echo '如需恢复：检出与备份匹配的旧版本，构建后执行 bash scripts/restore.sh 备份目录，输入 RESTORE。' >&2
}
trap failure ERR
bash "$ROOT/scripts/check-deployment.sh"
stop_writes
make_backup
# update.sh deliberately performs NO backup pruning.
PHASE=pull
git pull --ff-only
PHASE=build
"${DC[@]}" build
# From this point onward an old app must never restart against a migrated schema.
RESTART=0
PHASE=migration
"${DC[@]}" run --rm -T --no-deps backend alembic upgrade head
PHASE=start
"${DC[@]}" up -d --wait --wait-timeout 180
PHASE=health
"${DC[@]}" exec -T backend python -c 'import json, urllib.request; h=json.load(urllib.request.urlopen("http://localhost:8000/health", timeout=5)); assert h["postgres"] and h["redis"], h'
echo "更新完成：$(git rev-parse --short HEAD)。更新前备份：$LAST_BACKUP"
)
