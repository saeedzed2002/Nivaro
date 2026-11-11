#!/bin/sh
set -eu
umask 077
cat > /tmp/nivaro-cache.conf <<'CONF'
bind 0.0.0.0
port 6379
protected-mode yes
maxmemory 128mb
maxmemory-policy allkeys-lru
appendonly no
save ""
CONF
printf 'requirepass %s\n' "$(cat /run/secrets/redis_cache_password)" >> /tmp/nivaro-cache.conf
exec redis-server /tmp/nivaro-cache.conf
