#!/bin/sh
set -eu
# Official postgres entrypoint invokes this only for a new volume. Existing
# databases can run this same script explicitly; neither branch resets data.
catalog_password="$(cat /run/secrets/catalog_db_password)"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  --set=catalog_password="$catalog_password" <<'SQL'
SELECT format('CREATE ROLE nivaro_catalog LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION', :'catalog_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'nivaro_catalog') \gexec
SELECT 'CREATE DATABASE nivaro_catalog OWNER nivaro_catalog'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'nivaro_catalog') \gexec
REVOKE ALL ON DATABASE nivaro_catalog FROM PUBLIC;
GRANT CONNECT ON DATABASE nivaro_catalog TO nivaro_catalog;
SQL
