"""Run only in the disposable media QA stack; never mutate the owner's catalog."""

import asyncio
import io
import os
import sys
from uuid import UUID, uuid4

from PIL import Image
from sqlalchemy import select

from nivaro_catalog.application.media import queue_image
from nivaro_catalog.infrastructure.database import Database
from nivaro_catalog.infrastructure.media_storage import MediaStorage
from nivaro_catalog.infrastructure.models import MediaJobRow, MediaSlotRow, ProductRow
from nivaro_catalog.media_worker import app
from nivaro_catalog.settings import Settings


async def main():
    assert os.environ.get("NIVARO_MEDIA_QA") == "disposable", "Disposable opt-in required"
    dbs = Database(Settings())
    settings = Settings()
    storage = MediaStorage(settings.media_private_root, settings.media_output_root)
    try:
        async with dbs.sessions() as db:
            product = await db.scalar(select(ProductRow).order_by(ProductRow.id).limit(1))
            product_id = product.id

        async def queue(data):
            job = uuid4()
            storage.write_original(job, data)
            async with dbs.sessions() as db, db.begin():
                product = await db.get(ProductRow, product_id)
                await queue_image(
                    db,
                    product_id=product_id,
                    position=0,
                    expected_version=product.version,
                    job_id=job,
                    actor_id=uuid4(),
                    alt={"fa": "آزمون صف", "en": "Queue test"},
                    request_id="queue-qa",
                )
            return job

        async def state(job):
            async with dbs.sessions() as db:
                row = await db.get(MediaJobRow, job)
                return {
                    "state": row.state,
                    "attempts": row.attempts,
                    "error": row.error_code,
                    "outputs": row.outputs,
                }

        async def wait(job, expected, seconds=45):
            for _ in range(seconds * 4):
                result = await state(job)
                if result["state"] == expected:
                    return result
                if result["state"] == "failed" and expected != "failed":
                    raise AssertionError(result)
                await asyncio.sleep(0.25)
            raise AssertionError(await state(job))

        mode = sys.argv[1]
        if mode == "normal":
            buffer = io.BytesIO()
            Image.new("RGB", (1600, 900), (20, 80, 200)).save(buffer, "PNG")
            job = await queue(buffer.getvalue())
            ready = await wait(job, "ready")
            assert set(ready["outputs"]) == {"320", "640", "1280"}
            for width, path in ready["outputs"].items():
                with Image.open(storage.outputs / path) as image:
                    image.load()
                    assert image.format == "WEBP" and image.width == int(width)
            app.send_task(
                "catalog.process_image", args=[str(job), 1], task_id=str(job), queue="catalog.media"
            )
            await asyncio.sleep(2)
            assert (await state(job))["attempts"] == 1
            bad = await queue(b"<svg>forged upload</svg>")
            assert (await wait(bad, "failed"))["error"] == "invalid_image"
            async with dbs.sessions() as db:
                slot = await db.scalar(
                    select(MediaSlotRow).where(MediaSlotRow.product_id == product_id)
                )
                assert slot.active_job_id == job
            print(
                "MEDIA_QUEUE_OK: actual WebP outputs, duplicate delivery and failed replacement preserved"
            )
        elif mode == "large":
            # Real bounded decode/resize workload, no production delay hook.
            buffer = io.BytesIO()
            Image.effect_noise((6000, 4000), 80).convert("RGB").save(buffer, "JPEG", quality=15)
            assert len(buffer.getvalue()) <= 8 * 1024 * 1024
            job = await queue(buffer.getvalue())
            await wait(job, "processing", seconds=15)
            print(str(job), flush=True)
        elif mode == "recovered":
            job = UUID(sys.argv[2])
            ready = await wait(job, "ready", seconds=130)
            assert ready["attempts"] >= 2, ready
            print("MEDIA_WORKER_LOSS_OK: expired claim recovered and new attempt activated")
    finally:
        await dbs.engine.dispose()


asyncio.run(main())
