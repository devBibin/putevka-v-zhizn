#!/usr/bin/env bash
# Create a PostgreSQL archive from the production Compose stack and upload it
# to an rclone remote (normally an encrypted Yandex Disk remote).
set -euo pipefail

umask 077

: "${APP_DIR:?Set APP_DIR in /etc/putevka-backup.env}"
: "${BACKUP_DIR:?Set BACKUP_DIR in /etc/putevka-backup.env}"
: "${RCLONE_REMOTE:?Set RCLONE_REMOTE in /etc/putevka-backup.env}"
: "${RCLONE_PATH:?Set RCLONE_PATH in /etc/putevka-backup.env}"
: "${RETENTION_DAYS:?Set RETENTION_DAYS in /etc/putevka-backup.env}"

command -v docker >/dev/null
command -v rclone >/dev/null
command -v sha256sum >/dev/null

mkdir -p "$BACKUP_DIR"
work_dir="$(mktemp -d "$BACKUP_DIR/.backup.XXXXXX")"
trap 'rm -rf "$work_dir"' EXIT

timestamp="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
archive="putevka-postgres-${timestamp}.dump"
archive_path="$work_dir/$archive"
checksum_path="$archive_path.sha256"
remote_path="$RCLONE_REMOTE:$RCLONE_PATH"

cd "$APP_DIR"

# `pg_dump` runs inside the existing Postgres container, so the production
# database port and password never need to be exposed to the host.
docker compose exec -T db sh -ceu \
  'pg_dump --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --format=custom --no-owner --no-privileges' \
  > "$archive_path"

# A non-empty custom archive that pg_restore can list is a basic integrity
# check before it leaves the server.
test -s "$archive_path"
docker compose exec -T db pg_restore --list < "$archive_path" >/dev/null
sha256sum "$archive_path" > "$checksum_path"

rclone copy "$work_dir" "$remote_path" \
  --include "$archive" \
  --include "$archive.sha256" \
  --transfers 1 \
  --checkers 4 \
  --stats 30s \
  --stats-one-line \
  --log-level INFO

# Retention applies only inside the dedicated backup directory on the remote.
rclone delete "$remote_path" \
  --min-age "${RETENTION_DAYS}d" \
  --include '*.dump' \
  --include '*.dump.sha256'
rclone rmdirs "$remote_path" --leave-root

echo "Backup uploaded: $remote_path/$archive"
