#!/bin/sh
set -eu
umask 077
password=$(cat /run/secrets/redis_support_password)
test -n "$password"
digest=$(printf '%s' "$password" | sha256sum | cut -d ' ' -f 1)
cat > /tmp/nivaro-support-redis.conf <<CONF
bind 0.0.0.0
port 6379
protected-mode yes
maxmemory 64mb
maxmemory-policy noeviction
appendonly no
save ""
user default off
user support on #$digest resetchannels &nivaro.support.message.v1 +ping +publish +subscribe +unsubscribe
CONF
exec redis-server /tmp/nivaro-support-redis.conf "$@"
