"""Atomic, bounded OTP state. Never store a raw code, phone or IP in Redis.

Single standalone redis-state is intentional; this script is not Redis Cluster
compatible. Security keys must use noeviction and authenticated internal access.
"""

import secrets
from dataclasses import dataclass, field
from uuid import uuid4

from redis.asyncio import Redis

from nivaro_identity.domain.security import authenticate_value

_REQUEST = """
-- Check every limit before changing challenge state. IP requests include sends
-- denied by phone cooldown/limits, so rotating numbers cannot bypass IP limits.
local ip = redis.call('INCR', KEYS[4])
if ip == 1 then redis.call('EXPIRE', KEYS[4], 3600) end
if ip > tonumber(ARGV[3]) then return math.max(1, redis.call('TTL', KEYS[4])) end
local cooldown = redis.call('TTL', KEYS[1])
if cooldown > 0 then return cooldown end
if tonumber(redis.call('GET', KEYS[2]) or '0') >= 5 then
  return math.max(1, redis.call('TTL', KEYS[2]))
end
if tonumber(redis.call('GET', KEYS[3]) or '0') >= 30 then
  return math.max(1, redis.call('TTL', KEYS[3]))
end
for i = 2,3 do
  local count = redis.call('INCR', KEYS[i])
  if count == 1 then
    if i == 2 then redis.call('EXPIRE', KEYS[i], 3600)
    else redis.call('EXPIRE', KEYS[i], 86400) end
  end
end
redis.call('SET', KEYS[1], '1', 'EX', 60)
-- One challenge per phone/purpose: replacement invalidates the old ID.
redis.call('HSET', KEYS[5], 'id', ARGV[1], 'mac', ARGV[2], 'attempts', '0')
redis.call('EXPIRE', KEYS[5], 120)
return 0
"""

_VERIFY = """
if redis.call('HGET', KEYS[1], 'id') ~= ARGV[1] then return 0 end
local attempts = redis.call('HINCRBY', KEYS[1], 'attempts', 1)
if attempts > 5 then redis.call('DEL', KEYS[1]); return 0 end
if redis.call('HGET', KEYS[1], 'mac') ~= ARGV[2] then
  if attempts >= 5 then redis.call('DEL', KEYS[1]) end
  return 0
end
redis.call('DEL', KEYS[1])
return 1
"""


@dataclass(frozen=True)
class Challenge:
    id: str
    code: str = field(repr=False)


class RateLimited(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__("Try again later")


class OTP:
    def __init__(self, redis: Redis, pepper: str, ip_limit: int = 30):
        if len(pepper) < 32:
            raise ValueError("OTP HMAC requires a strong server key")
        self.redis = redis
        self.pepper = pepper
        self.ip_limit = ip_limit

    def phone_key(self, phone: str) -> str:
        return "identity:otp:" + authenticate_value(self.pepper, "phone", phone)

    async def request(self, phone: str, ip: str) -> Challenge:
        challenge = Challenge(str(uuid4()), f"{secrets.randbelow(1_000_000):06d}")
        base = self.phone_key(phone)
        ip_key = "identity:otp:ip:" + authenticate_value(self.pepper, "ip", ip)
        mac = authenticate_value(self.pepper, "customer-login", phone, challenge.id, challenge.code)
        retry_after = int(
            await self.redis.eval(
                _REQUEST,
                5,
                base + ":cooldown",
                base + ":hour",
                base + ":day",
                ip_key,
                base,
                challenge.id,
                mac,
                self.ip_limit,
            )
        )
        if retry_after:
            raise RateLimited(retry_after)
        return challenge

    async def verify(self, phone: str, challenge_id: str, code: str) -> bool:
        mac = authenticate_value(self.pepper, "customer-login", phone, challenge_id, code)
        return bool(await self.redis.eval(_VERIFY, 1, self.phone_key(phone), challenge_id, mac))
