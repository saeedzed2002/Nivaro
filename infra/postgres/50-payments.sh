#!/bin/sh
set -eu
export PGPASSWORD="$(cat /run/secrets/postgres_admin_password)"
payments_password="$(cat /run/secrets/payments_db_password)"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  --set=payments_password="$payments_password" <<'SQL'
SELECT format('CREATE ROLE nivaro_payments LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION', :'payments_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'nivaro_payments') \gexec
SELECT 'CREATE DATABASE nivaro_payments OWNER nivaro_payments'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'nivaro_payments') \gexec
REVOKE ALL ON DATABASE nivaro_payments FROM PUBLIC;
GRANT CONNECT ON DATABASE nivaro_payments TO nivaro_payments;
SQL
