#!/usr/bin/env bash
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
[[ "$RETENTION_DAYS" =~ ^[1-9][0-9]*$ ]] || { echo 'RETENTION_DAYS 必须为正整数'; exit 1; }
stop_writes
make_backup
# Only expire completed, recognizable backup sets; never touch partial files.
while IFS= read -r -d '' candidate; do
  [ "$candidate" = "$LAST_BACKUP" ] && continue
  [ -f "$candidate/manifest.txt" ] && [ -f "$candidate/SHA256SUMS" ] || continue
  rm -r -- "$candidate"
done < <(find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -name '20*T*Z-*' -mtime +"$RETENTION_DAYS" -print0)
