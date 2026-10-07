#!/bin/bash
set -e
for db in litellm n8n langfuse ouroboros; do
psql -v ON_ERROR_STOP=1 -U postgres <<SQL
CREATE USER $db WITH PASSWORD '$APP_DB_PASSWORD';
CREATE DATABASE $db OWNER $db;
SQL
done
psql -v ON_ERROR_STOP=1 -U postgres -d ouroboros -c "CREATE EXTENSION IF NOT EXISTS vector;"
