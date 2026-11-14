-- Apply only to the disposable cart acceptance database.
BEGIN;
DO $$
DECLARE fixture_variant uuid;
BEGIN
    SELECT v.id INTO STRICT fixture_variant
    FROM variants v JOIN products p ON p.id = v.product_id
    WHERE p.slug = 'amd-ryzen-7-9800x3d'
    ORDER BY v.sku LIMIT 1;

    UPDATE variants SET stock_verified = true, on_hand = 12, reserved = 0
    WHERE id = fixture_variant;

    UPDATE market_offers SET reference_only = false, available_for_sale = true,
        amount_minor = 45900, price_version = price_version + 1
    WHERE variant_id = fixture_variant AND market = 'international';
    IF NOT FOUND THEN RAISE EXCEPTION 'Missing seeded USD offer'; END IF;
END $$;
COMMIT;
