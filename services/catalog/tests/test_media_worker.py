import importlib


def test_worker_contract_and_scoped_topology(tmp_path, monkeypatch):
    secret = tmp_path / "broker-password"
    secret.write_text("disposable-nonproduction-secret")
    monkeypatch.setenv("CATALOG_MEDIA_BROKER_PASSWORD_FILE", str(secret))
    worker = importlib.import_module("nivaro_catalog.media_worker")
    assert set(worker.app.tasks) == {"catalog.process_image"}
    config = worker.app.conf
    assert config.accept_content == ["json"]
    assert config.task_acks_late and config.task_reject_on_worker_lost
    assert config.task_time_limit < 90
    assert config.broker_transport_options["confirm_publish"]
    queue = config.task_queues[0]
    assert queue.name == queue.exchange.name == "catalog.media"
    assert queue.queue_arguments == {"x-queue-type": "quorum"}
    assert not config.worker_enable_remote_control
    assert not any(
        "delayed_delivery" in step for step in worker.ImmediateMediaConsumer.Blueprint.default_steps
    )
