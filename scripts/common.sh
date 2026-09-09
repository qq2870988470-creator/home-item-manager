#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/env.sh"
mkdir -p "$BACKUP_ROOT"
# Atomic mkdir works on Linux/macOS and excludes concurrent backup/restore jobs.
LOCK="$BACKUP_ROOT/.maintenance-lock"
mkdir "$LOCK" 2>/dev/null || { echo '已有维护任务运行；若上次异常退出，请核实无任务后手工移除锁目录。' >&2; exit 1; }
RESTART=0
cleanup() {
  result=$?
  trap - EXIT
  if [ "$RESTART" = 1 ]; then "${DC[@]}" start backend || result=1; fi
  rmdir "$LOCK" || true
  exit "$result"
}
trap cleanup EXIT
stop_writes() {
  if [ -n "$("${DC[@]}" ps --status running -q backend)" ]; then
    RESTART=1
    "${DC[@]}" stop -t 60 backend
  fi
}
make_backup() {
  local name dest
  name="$(date -u +%Y%m%dT%H%M%SZ)-$$"
  dest="$BACKUP_ROOT/$name"
  mkdir "$dest.partial"
  "${DC[@]}" exec -T postgres sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$dest.partial/database.dump"
  "${DC[@]}" run --rm -T --no-deps backend python -m app.image_archive backup > "$dest.partial/images.tar.gz"
  "${DC[@]}" exec -T postgres pg_restore --list < "$dest.partial/database.dump" >/dev/null
  gzip -t "$dest.partial/images.tar.gz"
  "${DC[@]}" run --rm -T --no-deps backend python -m app.image_archive validate < "$dest.partial/images.tar.gz"
  (cd "$dest.partial" && checksum database.dump images.tar.gz > SHA256SUMS)
  printf 'home-item-manager-v1\nUTC=%s\n' "$name" > "$dest.partial/manifest.txt"
  mv "$dest.partial" "$dest"
  LAST_BACKUP="$dest"
  echo "备份完成：$dest"
}
