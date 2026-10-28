#!/bin/sh
set -eu
if [ -n "${PGHOST:-}" ]; then
  export PGPASSWORD="$(cat /run/secrets/postgres_admin_password)"
fi
identity_password="$(cat /run/secrets/identity_db_password)"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  --set=identity_password="$identity_password" <<'SQL'
SELECT format('CREATE ROLE nivaro_identity LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION', :'identity_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'nivaro_identity') \gexec
SELECT 'CREATE DATABASE nivaro_identity OWNER nivaro_identity'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'nivaro_identity') \gexec
REVOKE ALL ON DATABASE nivaro_identity FROM PUBLIC;
GRANT CONNECT ON DATABASE nivaro_identity TO nivaro_identity;
SQL
