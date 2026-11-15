import os
from uuid import uuid4

import httpx
import pytest

ORIGIN = "http://127.0.0.1:8082"
BASE_URL = "http://gateway:8080"
ORDERS = "/api/v1/orders"
MARKET = {"market": "international", "currency": "USD"}


def expect(response: httpx.Response, status: int = 200, code: str | None = None):
    assert response.status_code == status, (response.request.url.path, response.text)
    body = response.json()
    if code is not None:
        assert body["error"]["code"] == code
    return body


async def sign_in(client: httpx.AsyncClient, phone: str) -> None:
    challenge = expect(await client.post("/api/v1/auth/otp/request", json={"phone": phone}))
    session = expect(
        await client.post(
            "/api/v1/auth/otp/verify",
            json={
                "phone": phone,
                "challenge_id": challenge["challenge_id"],
                "code": challenge["development_code"],
            },
        )
    )
    client.headers["X-CSRF-Token"] = session["csrf_token"]


@pytest.mark.skipif(os.getenv("ORDERS_CHECKOUT_E2E") != "1", reason="Disposable gateway required")
async def test_gateway_checks_authoritative_checkout_and_order_ownership():
    async with (
        httpx.AsyncClient(base_url=BASE_URL, headers={"Origin": ORIGIN}) as customer,
        httpx.AsyncClient(base_url=BASE_URL, headers={"Origin": ORIGIN}) as other,
    ):
        assert (await other.post("/internal/v1/orders/checkout-context")).status_code == 404
        expect(await other.get(f"{ORDERS}/{uuid4()}"), 401, "session.invalid")
        await sign_in(customer, "+12025550100")
        await sign_in(other, "+12025550101")
        address_data = {
            "label": "Test delivery",
            "recipient": "Test Customer",
            "country": "US",
            "city": "Washington",
            "postal_code": "20001",
            "street": "10 Test Street",
            "phone": "+12025550100",
        }
        address = expect(await customer.post("/api/v1/me/addresses", json=address_data), 201)
        product = expect(await customer.get("/api/v1/catalog/products/amd-ryzen-7-9800x3d"))
        variant = min(product["variants"], key=lambda item: item["sku"])["id"]
        cart = expect(await customer.get("/api/v1/cart?market=international"))
        line = expect(
            await customer.post(
                "/api/v1/cart/items",
                json={
                    "market": "international",
                    "variant_id": variant,
                    "quantity": 1,
                    "expected_version": cart["version"],
                },
            ),
            201,
        )
        item_path = f"/api/v1/cart/items/{line['line_id']}"
        intent = {
            **MARKET,
            "cart_version": line["version"],
            "address_id": address["id"],
            "address_version": address["version"],
        }

        async def available_stock() -> int:
            summary = expect(
                await customer.post(
                    "/api/v1/catalog/variant-summaries", json={**MARKET, "variant_ids": [variant]}
                )
            )
            return summary["items"][0]["available_quantity"]

        async def preview(key: str):
            response = await customer.post(
                f"{ORDERS}/checkout/preview", json=intent, headers={"Idempotency-Key": key}
            )
            assert response.headers["Cache-Control"] == "no-store"
            return expect(response)

        async def confirm(client, review, confirmation=None):
            return await client.post(
                f"{ORDERS}/checkout/{review['operation_id']}/confirm",
                json={"confirmation": confirmation or review["confirmation"]},
            )

        key = str(uuid4())
        preview_path = f"{ORDERS}/checkout/preview"
        expect(
            await customer.post(
                preview_path, json=intent, headers={"Idempotency-Key": key, "X-CSRF-Token": "wrong"}
            ),
            403,
            "csrf.invalid",
        )
        expect(
            await customer.post(
                preview_path,
                json=intent,
                headers={"Idempotency-Key": key, "Origin": "https://invalid.example"},
            ),
            403,
            "origin.forbidden",
        )
        expect(
            await customer.post(
                preview_path, json={**intent, "totals": 1}, headers={"Idempotency-Key": key}
            ),
            422,
        )
        stock = await available_stock()
        first = await preview(key)
        assert await preview(key) == first
        assert await available_stock() == stock
        line = expect(
            await customer.patch(
                item_path,
                json={
                    "market": "international",
                    "quantity": 2,
                    "expected_version": line["version"],
                },
            )
        )
        expect(await confirm(customer, first), 409, "checkout.cart_changed")
        intent["cart_version"] = line["version"]
        second = await preview(str(uuid4()))
        address = expect(
            await customer.put(
                f"/api/v1/me/addresses/{address['id']}",
                json={**address_data, "version": address["version"], "street": "20 Test Street"},
            )
        )
        expect(await confirm(customer, second), 409, "checkout.address_changed")
        intent["address_version"] = address["version"]
        final = await preview(str(uuid4()))
        assert final["totals"]["total_minor"] == 92500
        assert final["lines"][0]["quantity"] == 2
        assert await available_stock() == stock
        expect(await confirm(customer, final, "0" * 64), 409, "checkout.confirmation_changed")
        expect(await confirm(other, final), 404, "checkout.not_found")
        order = expect(await confirm(customer, final))
        assert order["id"] == final["operation_id"]
        assert order["status"] == "awaiting_payment"
        assert order["totals"] == final["totals"]
        assert await available_stock() == stock - 2
        order_path = f"{ORDERS}/{order['id']}"
        expect(await other.get(order_path), 404, "checkout.not_found")
        response = await customer.get(order_path)
        assert response.headers["Cache-Control"] == "no-store"
        assert "Test Street" not in response.text
        assert expect(response) == order

        payment_path = order_path + "/payment"
        payment = {"order_version": order["version"]}
        payment_headers = {"Idempotency-Key": order["id"]}
        expect(
            await other.post(payment_path, json=payment, headers=payment_headers),
            404,
            "checkout.not_found",
        )
        expect(
            await customer.post(
                payment_path, json=payment, headers={**payment_headers, "X-CSRF-Token": "wrong"}
            ),
            403,
            "csrf.invalid",
        )
        expect(
            await customer.post(
                payment_path, json=payment, headers={"Idempotency-Key": str(uuid4())}
            ),
            422,
            "checkout.invalid_idempotency_key",
        )
        expect(
            await customer.post(
                payment_path, json={"order_version": order["version"] + 1}, headers=payment_headers
            ),
            409,
            "payment.order_changed",
        )
        expect(
            await customer.post(
                payment_path, json={**payment, "amount_minor": 1}, headers=payment_headers
            ),
            422,
            "request.invalid",
        )
        assert expect(await customer.get(order_path + "?payment=paid")) == order
        assert order["payment_state"] is None

        expect(
            await customer.patch(
                item_path,
                json={
                    "market": "international",
                    "quantity": 1,
                    "expected_version": line["version"],
                },
            )
        )
        assert expect(await confirm(customer, final)) == order
        assert await available_stock() == stock - 2
