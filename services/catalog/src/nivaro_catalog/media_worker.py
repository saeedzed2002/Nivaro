"""Dedicated prefork worker. Run with concurrency=1 and container memory/CPU limits."""

import asyncio
from urllib.parse import quote
from uuid import UUID

from celery import Celery
from celery.worker.consumer.consumer import Consumer
from kombu import Exchange, Queue
from nivaro_image_processing import InvalidImage, process_image

from nivaro_catalog.application.media import claim_job, finish_job
from nivaro_catalog.infrastructure.database import Database
from nivaro_catalog.infrastructure.media_storage import MediaStorage
from nivaro_catalog.settings import Settings


class ImmediateMediaConsumer(Consumer):  # type: ignore[misc]
    """Retries live in our durable dispatch table; this worker accepts no ETA tasks.

    Exclude Celery's native delayed-delivery topology instead of granting this
    narrowly scoped broker user access to an unrelated scheduler's exchanges.
    """

    class Blueprint(Consumer.Blueprint):  # type: ignore[misc]
        default_steps = [
            step
            for step in Consumer.Blueprint.default_steps
            if step != "celery.worker.consumer.delayed_delivery:DelayedDelivery"
        ]


def create_app(settings: Settings) -> Celery:
    password = settings.media_broker_password_file.read_text().strip()
    if not password:
        raise ValueError("Media broker password is required")
    broker = f"amqp://{quote(settings.media_broker_user, safe='')}:{quote(password, safe='')}@{settings.media_broker_host}:5672/catalog-media"
    app = Celery("nivaro_catalog_media", broker=broker)
    app.conf.update(
        task_queues=[
            Queue(
                "catalog.media",
                Exchange("catalog.media", type="topic", durable=True),
                routing_key="catalog.media",
                queue_arguments={"x-queue-type": "quorum"},
            )
        ],
        task_default_queue_type="quorum",
        worker_detect_quorum_queues=True,
        task_default_exchange_type="topic",
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        task_default_queue="catalog.media",
        task_default_exchange="catalog.media",
        task_default_routing_key="catalog.media",
        task_create_missing_queues=False,
        task_ignore_result=True,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_soft_time_limit=50,
        task_time_limit=60,
        broker_connection_timeout=3,
        broker_connection_retry_on_startup=True,
        broker_transport_options={"confirm_publish": True, "read_timeout": 5, "write_timeout": 5},
        task_publish_retry=False,
        worker_max_tasks_per_child=20,
        worker_max_memory_per_child=384000,
        worker_enable_remote_control=False,
        worker_consumer="nivaro_catalog.media_worker:ImmediateMediaConsumer",
    )
    return app


async def execute(job_id: UUID) -> None:
    settings = Settings()
    database = Database(settings)
    try:
        async with database.sessions() as db, db.begin():
            attempt = await claim_job(db, job_id)
        if attempt is None:
            return
        storage = MediaStorage(settings.media_private_root, settings.media_output_root)
        failure = None
        outputs = None
        try:
            processed = process_image(storage.read_original(job_id), purpose="product")
            paths = storage.write_outputs(
                attempt, {part.target: part.content for part in processed}
            )
            outputs = {str(width): path for width, path in paths.items()}
        except InvalidImage as exc:
            failure = exc.code
        # Filesystem/process/DB failure leaves the claim recoverable by the sweeper.
        async with database.sessions() as db, db.begin():
            await finish_job(db, job_id, attempt, outputs=outputs, error_code=failure)
    finally:
        await database.engine.dispose()


app = create_app(Settings())


@app.task(name="catalog.process_image", typing=True)  # type: ignore[untyped-decorator]
def process_job(job_id: str, contract_version: int) -> None:
    if contract_version != 1:
        raise ValueError("Unsupported media contract")
    asyncio.run(execute(UUID(job_id)))


# No generic canvas/result-maintenance tasks are accepted by this dedicated queue.
app.finalize()
for registered_name in list(app.tasks):
    if registered_name != "catalog.process_image":
        del app.tasks[registered_name]
