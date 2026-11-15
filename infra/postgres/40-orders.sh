#!/bin/sh
set -eu
export PGPASSWORD="$(cat /run/secrets/postgres_admin_password)"
orders_password="$(cat /run/secrets/orders_db_password)"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  --set=orders_password="$orders_password" <<'SQL'
SELECT format('CREATE ROLE nivaro_orders LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION', :'orders_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'nivaro_orders') \gexec
SELECT 'CREATE DATABASE nivaro_orders OWNER nivaro_orders'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'nivaro_orders') \gexec
REVOKE ALL ON DATABASE nivaro_orders FROM PUBLIC;
GRANT CONNECT ON DATABASE nivaro_orders TO nivaro_orders;
SQL
