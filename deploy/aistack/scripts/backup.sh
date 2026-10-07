#!/bin/bash
# Ежедневный бэкап: Postgres (все БД), n8n, данные Ouroboros, конфиги и секреты.
set -euo pipefail
source /opt/aistack/.backup.env          # RESTIC_REPOSITORY, RESTIC_PASSWORD (+ S3 креды при наличии)
export RESTIC_REPOSITORY RESTIC_PASSWORD
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
echo "backup ok $(date -Is)"
