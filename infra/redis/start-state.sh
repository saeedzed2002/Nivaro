#!/bin/sh
set -eu
umask 077
cat > /tmp/nivaro-redis.conf <<'CONF'
bind 0.0.0.0
port 6379
protected-mode yes
maxmemory 128mb
maxmemory-policy noeviction
appendonly yes
appendfsync always
dir /data
save ""
CONF
printf 'requirepass %s\n' "$(cat /run/secrets/redis_state_password)" >> /tmp/nivaro-redis.conf
exec redis-server /tmp/nivaro-redis.conf
