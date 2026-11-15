import asyncio
import os
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select

from nivaro_support.models import AssignmentRow, MessageOutboxRow, MessageRow
from nivaro_support.settings import Database, Settings

pytestmark = pytest.mark.skipif(
    os.getenv("SUPPORT_DISPOSABLE_TESTS") != "1", reason="Disposable support stack required"
)
ORIGIN = "http://127.0.0.1:8082"
CUSTOMER = "/api/v1/support/conversations"
STAFF = "/api/v1/admin/support/conversations"


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
            reply = {"client_message_id": str(uuid4()), "body": "Agent reply"}
            sent = await support.post(staff_history, headers=credentials[winner][1], json=reply)
            assert sent.status_code == 200 and sent.json()["sequence"] == 2
            page = (await support.get(history, headers=owner_headers, params={"limit": 1})).json()
            assert page["has_more"] and page["messages"] == [stored]
            last = (await support.get(history, headers=owner_headers, params={"after": 1})).json()
            assert not last["has_more"] and last["messages"] == [sent.json()]

            manager = credentials["manager"][1]
            assert (
                await support.put(
                    assignment,
                    headers=manager,
                    json={"agent_id": credentials["sales"][0], "expected_version": 2},
                )
            ).status_code == 403
            changed = await support.put(
                assignment,
                headers=manager,
                json={"agent_id": credentials[loser][0], "expected_version": 2},
            )
            assert changed.status_code == 200 and changed.json()["version"] == 3
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
                await support.post(history, headers=owner_headers, json=reply)
            ).status_code == 409
            assert (
                await support.post(history, headers=owner_headers, json=first_message)
            ).json() == stored

        async with database.sessions() as db:
            messages = select(MessageRow.id).where(MessageRow.conversation_id == cid)
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(MessageOutboxRow)
                    .where(MessageOutboxRow.message_id.in_(messages))
                )
                == 2
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
