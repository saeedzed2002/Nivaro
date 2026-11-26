-- Executed only against a disposable catalog database by Verify-CatalogCache.ps1.
BEGIN;

CREATE TEMP TABLE load_products ON COMMIT DROP AS
SELECT product.id AS source_id, sample.number,
       md5('load-product:' || product.id || ':' || sample.number)::uuid AS id
FROM products AS product
CROSS JOIN generate_series(1, 100) AS sample(number)
WHERE product.status = 'published' AND product.image_ready;

INSERT INTO products (id, slug, name, description, category_id, brand, status,
                      image, image_ready, image_kind, highlights, search_tokens, created_at)
SELECT fixture.id, 'load-' || source.slug || '-' || fixture.number,
       source.name || ' (QA ' || fixture.number || ')', source.description, source.category_id,
       source.brand, source.status, source.image, source.image_ready, source.image_kind,
       source.highlights, array_append(source.search_tokens, 'loadprobe'),
       source.created_at + fixture.number * interval '1 minute'
FROM load_products AS fixture
JOIN products AS source ON source.id = fixture.source_id;

CREATE TEMP TABLE load_variants ON COMMIT DROP AS
SELECT variant.id AS source_id, fixture.id AS product_id, fixture.number,
       md5('load-variant:' || variant.id || ':' || fixture.number)::uuid AS id
FROM variants AS variant
JOIN load_products AS fixture ON variant.product_id = fixture.source_id;

INSERT INTO variants (id, product_id, sku, packaging, specifications, spec_version, version,
                      evidence, stock_kind, on_hand, reserved, stock_verified)
SELECT fixture.id, fixture.product_id, 'LOAD-' || source.sku || '-' || fixture.number,
       source.packaging, source.specifications, source.spec_version, 1, source.evidence,
       source.stock_kind, source.on_hand, 0, source.stock_verified
FROM load_variants AS fixture
JOIN variants AS source ON source.id = fixture.source_id;

INSERT INTO market_offers (id, variant_id, market, currency, amount_minor, price_version,
                           available_for_sale, reference_only, source, seller)
SELECT md5('load-offer:' || offer.id || ':' || fixture.number)::uuid, fixture.id,
       offer.market, offer.currency, offer.amount_minor + fixture.number *
           CASE WHEN offer.market = 'ir' THEN 10000 ELSE 100 END,
       offer.price_version, false, true, offer.source, offer.seller
FROM load_variants AS fixture
JOIN market_offers AS offer ON offer.variant_id = fixture.source_id;

COMMIT;

ANALYZE products;
ANALYZE variants;
ANALYZE market_offers;
