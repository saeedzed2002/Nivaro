-- Synthetic records for the disposable release backup drill.
\connect nivaro_identity
INSERT INTO users (id, phone, name)
VALUES ('baca0000-0000-4000-8000-000000000001', '+12025550100', 'Restore Drill Customer');
INSERT INTO avatar_slots (id, user_id, kind, version, desired_job_id, active_job_id)
VALUES ('baca0000-0000-4000-8000-000000000002', 'baca0000-0000-4000-8000-000000000001',
        'customer', 1, 'baca0000-0000-4000-8000-000000000003', 'baca0000-0000-4000-8000-000000000003');
INSERT INTO avatar_jobs (id, slot_id, state, attempts, attempt_id, finished_at)
VALUES ('baca0000-0000-4000-8000-000000000003', 'baca0000-0000-4000-8000-000000000002',
        'ready', 1, 'baca0000-0000-4000-8000-000000000004', now());

\connect nivaro_catalog
INSERT INTO product_media_slots (id, product_id, position, alt, desired_job_id, active_job_id)
VALUES ('baca0000-0000-4000-8000-000000000010', (SELECT id FROM products WHERE slug = 'amd-ryzen-7-9800x3d'),
        0, '{"fa":"تصویر آزمون بازیابی", "en":"Restore drill image"}',
        'baca0000-0000-4000-8000-000000000011', 'baca0000-0000-4000-8000-000000000011');
INSERT INTO product_media_jobs (id, slot_id, actor_id, alt, image_kind, state, attempts, attempt_id, outputs, finished_at)
VALUES ('baca0000-0000-4000-8000-000000000011', 'baca0000-0000-4000-8000-000000000010',
        'baca0000-0000-4000-8000-000000000001', '{"fa":"تصویر آزمون بازیابی", "en":"Restore drill image"}',
        'illustration', 'ready', 1, 'baca0000-0000-4000-8000-000000000012',
        '{"320":"baca0000000040008000000000000012/320.webp"}', now());

\connect nivaro_cart
INSERT INTO owners (id, customer_id)
VALUES ('baca0000-0000-4000-8000-000000000020', 'baca0000-0000-4000-8000-000000000001');
INSERT INTO carts (id, owner_id, market, currency, version)
VALUES ('baca0000-0000-4000-8000-000000000021', 'baca0000-0000-4000-8000-000000000020',
        'international', 'USD', 1);

\connect nivaro_orders
INSERT INTO checkout_operations (id, customer_id, idempotency_key, fingerprint, intent, state)
VALUES ('baca0000-0000-4000-8000-000000000030', 'baca0000-0000-4000-8000-000000000001', 'restore-drill',
        repeat('1', 64), '{}', 'reservation_confirmed');
INSERT INTO orders (id, customer_id, status, version, cart_id, cart_version, cart_fingerprint, quote_id,
                    quote_expires_at, confirmation, market, currency, subtotal_minor, discount_minor,
                    shipping_minor, tax_minor, tax_included, total_minor, delivery_policy)
VALUES ('baca0000-0000-4000-8000-000000000030', 'baca0000-0000-4000-8000-000000000001', 'paid', 2,
        'baca0000-0000-4000-8000-000000000021', 1, repeat('2', 64), gen_random_uuid(),
        now(), repeat('3', 64), 'international', 'USD', 4200, 0, 500, 0, false, 4700, '{}');

\connect nivaro_payments
INSERT INTO payment_attempts (id, idempotency_key, fingerprint, order_id, order_version, market, currency,
                              amount_minor, reservation_expires_at, scenario, provider_reference, status,
                              version, captured_minor, verified_at)
VALUES ('baca0000-0000-4000-8000-000000000040', 'restore-drill', repeat('4', 64),
        'baca0000-0000-4000-8000-000000000030', 1, 'international', 'USD', 4700, now(),
        'success', 'sim-restore-drill', 'succeeded', 2, 4700, now());

\connect nivaro_support
INSERT INTO conversations (id, customer_id, client_conversation_id, subject, last_sequence)
VALUES ('baca0000-0000-4000-8000-000000000050', 'baca0000-0000-4000-8000-000000000001',
        gen_random_uuid(), 'Restore drill conversation', 1);
INSERT INTO messages (id, conversation_id, sender_id, sender_kind, client_message_id, sequence, body)
VALUES ('baca0000-0000-4000-8000-000000000051', 'baca0000-0000-4000-8000-000000000050',
        'baca0000-0000-4000-8000-000000000001', 'customer', gen_random_uuid(), 1, 'پیام آزمایشی بازیابی');
