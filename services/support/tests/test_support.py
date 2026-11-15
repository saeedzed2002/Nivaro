import asyncio
import json
import os
from uuid import UUID, uuid4

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import func, select
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosedError, InvalidStatus

from nivaro_support.live import CHANNEL
from nivaro_support.models import AssignmentRow, MessageOutboxRow, MessageRow
from nivaro_support.settings import Database, Settings
from nivaro_support.socket_contracts import SERVER

pytestmark = pytest.mark.skipif(
    os.getenv("SUPPORT_DISPOSABLE_TESTS") != "1", reason="Disposable support stack required"
)
ORIGIN = "http://127.0.0.1:8082"
CUSTOMER = "/api/v1/support/conversations"
STAFF = "/api/v1/admin/support/conversations"
SOCKET = "ws://support:8000/ws/support"
REPLICA_SOCKET = "ws://support-replica:8000/ws/support"
STAFF_PROTOCOL = "nivaro.support.staff.v1"


def open_socket(headers=None, *, origin=ORIGIN, subprotocols=None, endpoint=SOCKET):
    return connect(
        endpoint,
        origin=origin,
        additional_headers={"Cookie": headers["Cookie"]} if headers else None,
        subprotocols=subprotocols,
        open_timeout=5,
        close_timeout=2,
        proxy=None,
    )


def frame(kind, conversation, payload, **references):
    return {
        "type": kind,
        "schema_version": 1,
        "request_id": str(uuid4()),
        "conversation_id": conversation,
        "payload": payload,
        **references,
    }


async def exchange(socket, request):
    await socket.send(json.dumps(request))
    response = await receive(socket)
    assert response["request_id"] == request["request_id"]
    return response


async def receive(socket, timeout=8):
    return SERVER.validate_json(await asyncio.wait_for(socket.recv(), timeout)).model_dump(
        mode="json"
    )


async def receive_created(socket, accepted):
    result = await receive(socket)
    assert result["type"] == "message.created"
    assert result["conversation_id"] == accepted["conversation_id"]
    assert result["payload"]["id"] == accepted["payload"]["message_id"]
    assert result["payload"]["sequence"] == accepted["payload"]["sequence"]
    return result["payload"]


def send_frame(conversation, body):
    return frame("message.send", conversation, {"body": body}, client_message_id=str(uuid4()))


async def wait_for_replicas(redis):
    async with asyncio.timeout(8):
        while dict(await redis.pubsub_numsub(CHANNEL)).get(CHANNEL) != 2:
            await asyncio.sleep(0.1)


async def verify_redis_recovery(db, owner_headers, agent_headers, conversation):
    async with (
        Redis(
            host="redis-support",
            username="support_qa",
            password=os.environ["NIVARO_QA_SUPPORT_REDIS_PASSWORD"],
            decode_responses=True,
            socket_timeout=2,
        ) as redis,
        open_socket(owner_headers) as customer,
        open_socket(agent_headers, subprotocols=[STAFF_PROTOCOL], endpoint=REPLICA_SOCKET) as agent,
    ):
        await wait_for_replicas(redis)
        subscribed = await exchange(
            agent, frame("conversation.subscribe", conversation, {"after": 2})
        )
        assert subscribed["payload"]["messages"] == []
        customer_message = await exchange(
            customer, send_frame(conversation, "Live customer message")
        )
        assert customer_message["payload"]["sequence"] == 3
        assert (await receive_created(agent, customer_message))["body"] == "Live customer message"

        await redis.execute_command("ACL", "SETUSER", "support", "off")
        try:
            assert await redis.execute_command("CLIENT", "KILL", "USER", "support") >= 2
            assert dict(await redis.pubsub_numsub(CHANNEL)).get(CHANNEL) == 0
            offline = await exchange(
                customer, send_frame(conversation, "Persisted during Redis outage")
            )
            assert offline["type"] == "message.accepted" and offline["payload"]["sequence"] == 4
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(agent.recv(), timeout=0.35)
            async with db.sessions() as session:
                outbox = await session.get(MessageOutboxRow, UUID(offline["payload"]["message_id"]))
                assert outbox is not None and outbox.published_at is None
            async with open_socket(
                agent_headers, subprotocols=[STAFF_PROTOCOL], endpoint=REPLICA_SOCKET
            ) as reconnected:
                result = await exchange(
                    reconnected, frame("sync.request", conversation, {"after": 3})
                )
                assert [message["id"] for message in result["payload"]["messages"]] == [
                    offline["payload"]["message_id"]
                ]
        finally:
            await redis.execute_command("ACL", "SETUSER", "support", "on")

        assert (await receive_created(agent, offline))["body"] == "Persisted during Redis outage"
        await wait_for_replicas(redis)
        async with asyncio.timeout(8):
            while True:
                async with db.sessions() as session:
                    row = await session.get(
                        MessageOutboxRow, UUID(offline["payload"]["message_id"])
                    )
                    if row is not None and row.published_at is not None:
                        break
                await asyncio.sleep(0.1)


async def customer_login(client, phone):
    challenge = await client.post("/api/v1/auth/otp/request", json={"phone": phone})
    assert challenge.status_code == 200, challenge.text
    otp = challenge.json()
    result = await client.post(
        "/api/v1/auth/otp/verify",
        json={
            "phone": phone,
            "challenge_id": otp["challenge_id"],
            "code": otp["development_code"],
        },
    )
    assert result.status_code == 200, result.text
    return result.json()


async def staff_login(client, role):
    result = await client.post(
        "/api/v1/admin/auth/login",
        json={
            "email": f"{role}@example.com",
            "password": os.environ["SUPPORT_TEST_PASSWORD"],
        },
    )
    assert result.status_code == 200, result.text
    return result.json()


async def test_private_history_assignment_and_idempotent_delivery():
    settings = Settings()
    assert settings.db_host.startswith("nivaro-support-qa-")
    database = Database(settings)
    try:
        async with (
            httpx.AsyncClient(
                base_url="http://identity:8000", headers={"Origin": ORIGIN}, trust_env=False
            ) as identity,
            httpx.AsyncClient(
                base_url="http://support:8000", trust_env=False, timeout=10
            ) as support,
        ):
            owner = await customer_login(identity, "+12025550100")
            owner_cookie = identity.cookies["nivaro_customer_access"]
            other = await customer_login(identity, "+12025550101")
            other_cookie = identity.cookies["nivaro_customer_access"]
            credentials = {}
            for role in ("first", "second", "sales", "manager"):
                principal = await staff_login(identity, role)
                credentials[role] = (
                    principal["profile"]["id"],
                    {
                        "Origin": ORIGIN,
                        "X-CSRF-Token": principal["csrf_token"],
                        "Cookie": f"nivaro_admin_access={identity.cookies['nivaro_admin_access']}",
                    },
                )
            owner_headers = {
                "Origin": ORIGIN,
                "X-CSRF-Token": owner["csrf_token"],
                "Cookie": f"nivaro_customer_access={owner_cookie}",
            }
            other_headers = {
                "Origin": ORIGIN,
                "X-CSRF-Token": other["csrf_token"],
                "Cookie": f"nivaro_customer_access={other_cookie}",
            }
            assertion = await support.get(CUSTOMER)
            assert assertion.status_code == 401 and assertion.headers["cache-control"] == "no-store"
            assert (await support.get(STAFF, headers=credentials["sales"][1])).status_code == 403
            for connection, code in (
                (open_socket(), 401),
                (open_socket(owner_headers, origin=None), 403),
                (open_socket(owner_headers, origin="https://other.test"), 403),
                (open_socket(credentials["sales"][1], subprotocols=[STAFF_PROTOCOL]), 403),
            ):
                with pytest.raises(InvalidStatus) as denied:
                    async with connection:
                        pytest.fail("Unauthorized WebSocket upgrade")
                assert denied.value.response.status_code == code

            creation = {"subject": "Help with an order", "client_conversation_id": str(uuid4())}
            assert (
                await support.post(
                    CUSTOMER,
                    headers={**owner_headers, "Origin": "https://other.test"},
                    json=creation,
                )
            ).status_code == 403
            created = await asyncio.gather(
                *(support.post(CUSTOMER, headers=owner_headers, json=creation) for _ in range(4))
            )
            assert all(result.status_code == 200 for result in created), [
                result.text for result in created
            ]
            conversation = created[0].json()
            assert len({result.json()["id"] for result in created}) == 1
            cid = conversation["id"]
            history = f"{CUSTOMER}/{cid}/messages"
            staff_history = f"{STAFF}/{cid}/messages"
            assignment = f"{STAFF}/{cid}/assignment"
            assert (await support.get(history, headers=other_headers)).status_code == 404
            assert (
                await support.get(CUSTOMER, headers=other_headers, params={"before": cid})
            ).status_code == 404
            assert (
                await support.get(staff_history, headers=credentials["first"][1])
            ).status_code == 404
            staff_queue = await support.get(STAFF, headers=credentials["first"][1])
            assert [row["id"] for row in staff_queue.json()["conversations"]] == [cid]

            def claim(role):
                agent, headers = credentials[role]
                return support.put(
                    assignment, headers=headers, json={"agent_id": agent, "expected_version": 1}
                )

            claims = await asyncio.gather(claim("first"), claim("second"))
            assert sorted(result.status_code for result in claims) == [200, 404]
            assigned = next(result.json() for result in claims if result.status_code == 200)
            winner = (
                "first" if assigned["assigned_agent_id"] == credentials["first"][0] else "second"
            )
            loser = "second" if winner == "first" else "first"
            first_message = {
                "client_message_id": str(uuid4()),
                "body": "<b>Literal customer text</b>",
            }
            assert (
                await support.post(
                    history,
                    headers=owner_headers,
                    json={**first_message, "sender_id": str(uuid4())},
                )
            ).status_code == 422
            messages = await asyncio.gather(
                *(
                    support.post(history, headers=owner_headers, json=first_message)
                    for _ in range(6)
                )
            )
            assert all(response.status_code == 200 for response in messages), [
                response.text for response in messages
            ]
            assert len({response.json()["id"] for response in messages}) == 1
            stored = messages[0].json()
            assert (stored["sequence"], stored["body"], stored["sender_id"]) == (
                1,
                first_message["body"],
                owner["profile"]["id"],
            )
            assert (
                await support.post(
                    history, headers=owner_headers, json={**first_message, "body": "Different text"}
                )
            ).status_code == 409
            assert (
                await support.get(staff_history, headers=credentials[loser][1])
            ).status_code == 404
            subscription = frame("conversation.subscribe", cid, {"after": 0})
            async with open_socket(other_headers) as outside:
                assert (await exchange(outside, subscription))["payload"] == {
                    "code": "support.not_found"
                }
                await outside.send("x" * 16385)
                with pytest.raises(ConnectionClosedError) as oversized:
                    await asyncio.wait_for(outside.recv(), timeout=5)
                assert oversized.value.rcvd is not None and oversized.value.rcvd.code == 1009

            async with (
                open_socket(owner_headers) as customer,
                open_socket(
                    credentials[winner][1], subprotocols=[STAFF_PROTOCOL], endpoint=REPLICA_SOCKET
                ) as agent,
            ):
                initial = await exchange(customer, subscription)
                assert initial["type"] == "sync.result" and initial["payload"]["messages"] == [
                    stored
                ]
                sending = send_frame(cid, "Agent reply")
                assert agent.subprotocol == STAFF_PROTOCOL
                rejected = await exchange(agent, {**sending, "sender_id": str(uuid4())})
                assert rejected["payload"] == {"code": "request.invalid"}
                assert rejected["client_message_id"] == sending["client_message_id"]
                accepted = await exchange(agent, sending)
                assert accepted["type"] == "message.accepted"
                assert accepted["payload"]["sequence"] == 2
                assert (await receive_created(customer, accepted))["body"] == "Agent reply"

            async with (
                open_socket(owner_headers) as customer,
                open_socket(
                    credentials[winner][1], subprotocols=[STAFF_PROTOCOL], endpoint=REPLICA_SOCKET
                ) as agent,
            ):
                retried = await exchange(agent, {**sending, "request_id": str(uuid4())})
                assert retried["payload"] == accepted["payload"]
                recovered = await exchange(customer, frame("sync.request", cid, {"after": 1}))
                assert recovered["type"] == "sync.result"
                assert [message["id"] for message in recovered["payload"]["messages"]] == [
                    accepted["payload"]["message_id"]
                ]
            page = (await support.get(history, headers=owner_headers, params={"limit": 1})).json()
            assert page["has_more"] and page["messages"] == [stored]
            last = (await support.get(history, headers=owner_headers, params={"after": 1})).json()
            assert not last["has_more"] and last["messages"] == recovered["payload"]["messages"]
            await verify_redis_recovery(database, owner_headers, credentials[winner][1], cid)

            manager = credentials["manager"][1]
            assert (
                await support.put(
                    assignment,
                    headers=manager,
                    json={"agent_id": credentials["sales"][0], "expected_version": 2},
                )
            ).status_code == 403
            async with open_socket(
                credentials[winner][1], subprotocols=[STAFF_PROTOCOL], endpoint=REPLICA_SOCKET
            ) as agent:
                prior = await exchange(agent, frame("conversation.subscribe", cid, {"after": 4}))
                assert prior["type"] == "sync.result"
                changed = await support.put(
                    assignment,
                    headers=manager,
                    json={"agent_id": credentials[loser][0], "expected_version": 2},
                )
                assert changed.status_code == 200 and changed.json()["version"] == 3
                marker = await support.post(
                    history,
                    headers=owner_headers,
                    json={"client_message_id": str(uuid4()), "body": "Private after reassignment"},
                )
                assert marker.status_code == 200 and marker.json()["sequence"] == 5
                with pytest.raises(TimeoutError):
                    await asyncio.wait_for(agent.recv(), timeout=0.5)
                assert (await exchange(agent, subscription))["payload"] == {
                    "code": "support.not_found"
                }
            assert (
                await support.get(staff_history, headers=credentials[winner][1])
            ).status_code == 404
            status = await support.put(
                f"{STAFF}/{cid}/status",
                headers=credentials[loser][1],
                json={"status": "closed", "expected_version": 3},
            )
            assert status.status_code == 200 and status.json()["closed_at"] is not None
            assert (
                await support.post(
                    history,
                    headers=owner_headers,
                    json={"client_message_id": str(uuid4()), "body": "Closed conversation"},
                )
            ).status_code == 409
            assert (
                await support.post(history, headers=owner_headers, json=first_message)
            ).json() == stored
            async with open_socket(owner_headers) as customer, open_socket(owner_headers) as idle:
                logged_out = await identity.post(
                    "/api/v1/auth/logout", headers=owner_headers, json={"all_devices": False}
                )
                assert logged_out.status_code == 200, logged_out.text
                denied = await exchange(customer, subscription)
                assert denied["payload"] == {"code": "auth.required"}
                with pytest.raises(ConnectionClosedError) as closed:
                    await asyncio.wait_for(customer.recv(), timeout=8)
                assert closed.value.rcvd is not None and closed.value.rcvd.code == 4401
                with pytest.raises(ConnectionClosedError) as idle_closed:
                    await asyncio.wait_for(idle.recv(), timeout=30)
                assert idle_closed.value.rcvd is not None and idle_closed.value.rcvd.code == 4401

        async with database.sessions() as db:
            messages = select(MessageRow.id).where(MessageRow.conversation_id == cid)
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(MessageOutboxRow)
                    .where(MessageOutboxRow.message_id.in_(messages))
                )
                == 5
            )
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(AssignmentRow)
                    .where(AssignmentRow.conversation_id == cid)
                )
                == 2
            )
    finally:
        await database.engine.dispose()
