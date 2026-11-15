#!/bin/sh
set -eu
export PGPASSWORD="$(cat /run/secrets/postgres_admin_password)"
support_password="$(cat /run/secrets/support_db_password)"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  --set=support_password="$support_password" <<'SQL'
SELECT format('CREATE ROLE nivaro_support LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION', :'support_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'nivaro_support') \gexec
SELECT 'CREATE DATABASE nivaro_support OWNER nivaro_support'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'nivaro_support') \gexec
REVOKE ALL ON DATABASE nivaro_support FROM PUBLIC;
GRANT CONNECT ON DATABASE nivaro_support TO nivaro_support;
SQL
