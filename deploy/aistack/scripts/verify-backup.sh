#!/bin/bash
# Проверка бэкапа: целостность репозитория + реальное восстановление дампа Postgres во временный контейнер.
set -euo pipefail
set -a; source /opt/aistack/.backup.env; set +a
# Проверяем именно внешнюю копию (S3), если она настроена
[ -n "${S3_REPOSITORY:-}" ] && export RESTIC_REPOSITORY=$S3_REPOSITORY
echo "repo: $RESTIC_REPOSITORY"
restic check --read-data-subset=10%
T=$(mktemp -d); trap 'rm -rf "$T"; docker rm -f pg-restore-test >/dev/null 2>&1 || true' EXIT
restic restore latest --target "$T" --include /var/backups/aistack-stage/postgres_all.sql.gz
docker run -d --name pg-restore-test -e POSTGRES_PASSWORD=test pgvector/pgvector:pg16 >/dev/null
for i in $(seq 1 30); do docker exec pg-restore-test pg_isready -U postgres >/dev/null 2>&1 && break; sleep 2; done
sleep 3
gunzip -c "$T/var/backups/aistack-stage/postgres_all.sql.gz" | docker exec -i pg-restore-test psql -q -U postgres >/dev/null 2>"$T/err" || true
for db in litellm n8n langfuse ouroboros; do
  n=$(docker exec pg-restore-test psql -U postgres -d $db -tAc "select count(*) from information_schema.tables where table_schema='public'")
  echo "$db: $n tables"; [ "$db" = ouroboros ] || [ "$n" -gt 0 ]
done
echo "verify ok $(date -Is)"
