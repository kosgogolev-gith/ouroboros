#!/bin/bash
# Ежедневный бэкап: Postgres (все БД), n8n, данные Ouroboros, конфиги и секреты.
set -euo pipefail
set -a; source /opt/aistack/.backup.env; set +a   # локальный репозиторий + S3_REPOSITORY и креды S3
STAGE=/var/backups/aistack-stage; rm -rf "$STAGE"; mkdir -p "$STAGE"
cd /opt/aistack
docker compose exec -T postgres pg_dumpall -U postgres | gzip > "$STAGE/postgres_all.sql.gz"
docker run --rm -v aistack_n8n_data:/src:ro -v "$STAGE":/dst alpine tar czf /dst/n8n_data.tgz -C /src .
restic snapshots >/dev/null 2>&1 || restic init
restic backup --tag daily --host aistack \
  "$STAGE" /opt/aistack/docker-compose.yml /opt/aistack/.env /opt/aistack/litellm /opt/aistack/caddy /opt/aistack/scripts \
  /home/goga/ouroboros_data /home/goga/.ouroboros.env /home/goga/vps_launcher.py /etc/systemd/system/ouroboros.service
restic forget --prune --keep-daily 7 --keep-weekly 4 --keep-monthly 6
rm -rf "$STAGE"
# Копия вне VM (S3)
if [ -n "${S3_REPOSITORY:-}" ]; then
  RESTIC_FROM_REPOSITORY=$RESTIC_REPOSITORY RESTIC_FROM_PASSWORD=$RESTIC_PASSWORD \
    restic -r "$S3_REPOSITORY" copy --from-repo "$RESTIC_REPOSITORY"
  restic -r "$S3_REPOSITORY" forget --prune --keep-daily 14 --keep-weekly 8 --keep-monthly 12
fi
echo "backup ok $(date -Is)"
