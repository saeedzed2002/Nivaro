"""Integration tests against an explicitly supplied disposable Redis instance.

No FLUSHDB, shared-secret inspection or persistent application-state mutation.
Each test uses a random HMAC pepper and only touches its own derived keys.
"""

import asyncio
import os
import secrets
from pathlib import Path

import pytest
from redis.asyncio import Redis
from redis.exceptions import ConnectionError, TimeoutError

from nivaro_identity.domain.security import authenticate_value
from nivaro_identity.infrastructure.otp import OTP, RateLimited

pytestmark = pytest.mark.skipif(
    not os.getenv("IDENTITY_TEST_REDIS_URL"), reason="Explicit disposable Redis URL required"
)
PHONE = "+12025550100"
IP = "192.0.2.1"


@pytest.fixture
async def otp():
    client = Redis.from_url(
        os.environ["IDENTITY_TEST_REDIS_URL"],
        password=Path(os.environ["IDENTITY_TEST_REDIS_PASSWORD_FILE"]).read_text().strip()
        if os.getenv("IDENTITY_TEST_REDIS_PASSWORD_FILE")
        else None,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    instance = OTP(client, secrets.token_hex(32))
    try:
        yield instance
    finally:
        await client.aclose()


async def test_twenty_racing_verifications_consume_exactly_once(otp):
    challenge = await otp.request(PHONE, IP)
    results = await asyncio.gather(
        *(otp.verify(PHONE, challenge.id, challenge.code) for _ in range(20))
    )
    assert sum(results) == 1
    assert not await otp.redis.exists(otp.phone_key(PHONE))


async def test_wrong_attempts_are_atomic_and_exhaust_challenge(otp):
    challenge = await otp.request(PHONE, IP)
    wrong = "000000" if challenge.code != "000000" else "111111"
    assert not any(
        await asyncio.gather(*(otp.verify(PHONE, challenge.id, wrong) for _ in range(20)))
    )
    assert not await otp.verify(PHONE, challenge.id, challenge.code)


async def test_fifth_attempt_can_succeed_but_sixth_cannot(otp):
    challenge = await otp.request(PHONE, IP)
    wrong = "invalid"
    for _ in range(4):
        assert not await otp.verify(PHONE, challenge.id, wrong)
    assert await otp.verify(PHONE, challenge.id, challenge.code)


async def test_replacement_invalidates_prior_code_and_expiry_is_enforced(otp):
    first = await otp.request(PHONE, IP)
    await otp.redis.delete(otp.phone_key(PHONE) + ":cooldown")
    second = await otp.request(PHONE, IP)
    assert not await otp.verify(PHONE, first.id, first.code)
    await otp.redis.expire(otp.phone_key(PHONE), 0)
    assert not await otp.verify(PHONE, second.id, second.code)


async def test_racing_resends_create_one_challenge(otp):
    results = await asyncio.gather(
        *(otp.request(PHONE, IP) for _ in range(20)), return_exceptions=True
    )
    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert sum(isinstance(result, RateLimited) for result in results) == 19
    assert await otp.redis.get(otp.phone_key(PHONE) + ":hour") == "1"


async def test_phone_hour_and_day_limits_survive_ip_changes(otp):
    for i in range(5):
        await otp.request(PHONE, f"192.0.2.{i}")
        await otp.redis.delete(otp.phone_key(PHONE) + ":cooldown")
    with pytest.raises(RateLimited):
        await otp.request(PHONE, "198.51.100.1")
    await otp.redis.delete(otp.phone_key(PHONE) + ":hour")
    await otp.redis.set(otp.phone_key(PHONE) + ":day", 30, ex=86400)
    with pytest.raises(RateLimited):
        await otp.request(PHONE, "198.51.100.2")


async def test_source_limit_survives_phone_changes(otp):
    otp.ip_limit = 3
    for i in range(3):
        await otp.request(f"+1202555010{i}", IP)
    with pytest.raises(RateLimited):
        await otp.request("+12025550109", IP)


async def test_redis_contains_only_authenticated_code_not_phone_ip_or_raw_code(otp):
    challenge = await otp.request(PHONE, IP)
    assert len(challenge.code) == 6 and challenge.code.isascii() and challenge.code.isdigit()
    assert challenge.code not in repr(challenge)
    value = await otp.redis.hgetall(otp.phone_key(PHONE))
    assert set(value) == {"id", "mac", "attempts"}
    assert value["mac"] == authenticate_value(
        otp.pepper, "customer-login", PHONE, challenge.id, challenge.code
    )
    assert value["mac"] != challenge.code
    assert PHONE not in otp.phone_key(PHONE)
    ttl = await otp.redis.ttl(otp.phone_key(PHONE))
    assert 1 <= ttl <= 120


async def test_challenge_and_phone_substitution_cannot_authenticate(otp):
    first = await otp.request(PHONE, IP)
    other_phone = "+12025550101"
    second = await otp.request(other_phone, IP)
    assert not await otp.verify(other_phone, first.id, first.code)
    assert not await otp.verify(PHONE, second.id, second.code)
    assert await otp.verify(PHONE, first.id, first.code)
    assert await otp.verify(other_phone, second.id, second.code)


async def test_unavailable_redis_fails_closed():
    client = Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.1, socket_timeout=0.1)
    try:
        instance = OTP(client, secrets.token_hex(32))
        with pytest.raises((ConnectionError, TimeoutError)):
            await instance.request(PHONE, IP)
        with pytest.raises((ConnectionError, TimeoutError)):
            await instance.verify(PHONE, "challenge", "123456")
    finally:
        await client.aclose()
