#!/bin/sh
set -eu
# Official postgres entrypoint invokes this only for a new volume. Existing
# databases can run this same script explicitly; neither branch resets data.
if [ -n "${PGHOST:-}" ]; then
  export PGPASSWORD="$(cat /run/secrets/postgres_admin_password)"
fi
cart_password="$(cat /run/secrets/cart_db_password)"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  --set=cart_password="$cart_password" <<'SQL'
SELECT format('CREATE ROLE nivaro_cart LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION', :'cart_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'nivaro_cart') \gexec
SELECT 'CREATE DATABASE nivaro_cart OWNER nivaro_cart'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'nivaro_cart') \gexec
REVOKE ALL ON DATABASE nivaro_cart FROM PUBLIC;
GRANT CONNECT ON DATABASE nivaro_cart TO nivaro_cart;
SQL
