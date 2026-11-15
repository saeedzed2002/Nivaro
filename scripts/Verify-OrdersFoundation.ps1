param(
    [string]$OrdersImage = 'nivaro-orders:release',
    [string]$TestImage = 'nivaro-orders:test',
    [string]$CatalogImage = 'nivaro-catalog:release',
    [string]$IdentityImage = 'nivaro-identity:release',
    [string]$WebImage = 'nivaro-web:release',
    [switch]$WithCatalog,
    [switch]$WithEvents,
    [switch]$WithPaymentResults,
    [switch]$WithCheckout,
    [switch]$Browser
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$project = 'nivaro-orders-qa-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
$config = @('-p', $project, '-f', "$root/compose.yaml", '-f', "$root/compose.identity-qa.yaml", '-f', "$root/compose.orders.yaml")
$previousImage = $env:NIVARO_ORDERS_IMAGE
$previousCatalogImage = $env:NIVARO_CART_QA_CATALOG_IMAGE
$previousIdentityImage = $env:NIVARO_CART_QA_IDENTITY_IMAGE
$previousPublisherImage = $env:NIVARO_EVENT_CATALOG_IMAGE
$previousRates = $env:NIVARO_ORDERS_DELIVERY_RATES
$previousPhones = $env:NIVARO_QA_MOCK_PHONES
$previousWebImage = $env:NIVARO_CART_QA_WEB_IMAGE
$previousBrowserUrl = $env:TEST_BASE_URL
$previousBrowserProject = $env:NIVARO_CHECKOUT_QA_PROJECT
if ($project -notmatch '^nivaro-orders-qa-[a-f0-9]{8}$') { throw 'Unsafe test project.' }
if ($Browser) { $WithCheckout = $true }
if ($WithPaymentResults) { $WithEvents = $true }
if ($WithEvents) {
    $config += @('-f', "$root/compose.media.yaml")
}
if ($WithEvents -or $WithCheckout) { $WithCatalog = $true }
if ($WithCatalog) { $config += @('-f', "$root/compose.cart-qa.yaml") }
if ($WithEvents) { $config += @('-f', "$root/compose.events.yaml") }
if ($WithPaymentResults) { $config += @('-f', "$root/compose.payments.yaml", '-f', "$root/compose.payment-events.yaml") }
if ($WithCheckout) {
    $env:NIVARO_ORDERS_DELIVERY_RATES = '[{"market":"international","currency":"USD","country":"US","policy_version":"synthetic-checkout-test","shipping_minor":700,"tax_basis_points":0,"tax_included":false,"shipping_taxable":false}]'
}
try {
    & "$PSScriptRoot/Initialize-LocalSecrets.ps1"
    $env:NIVARO_ORDERS_IMAGE = $OrdersImage
    if ($Browser) {
        $env:NIVARO_QA_MOCK_PHONES = '["+12025550100","+12025550101","+12025550102"]'
        $env:NIVARO_CART_QA_WEB_IMAGE = $WebImage
    }
    $services = @('orders')
    if ($WithCatalog) {
        $env:NIVARO_CART_QA_CATALOG_IMAGE = $CatalogImage
        $env:NIVARO_CART_QA_IDENTITY_IMAGE = $IdentityImage
        $services += @('catalog', 'identity', 'redis-cache')
    }
    if ($WithCheckout) { $services += @('cart', 'gateway') }
    if ($WithEvents) {
        & "$PSScriptRoot/Initialize-MediaSecrets.ps1"
        $env:NIVARO_EVENT_CATALOG_IMAGE = $CatalogImage
        $services += @('catalog-event-publisher', 'orders-expiry-consumer')
    }
    if ($WithPaymentResults) { $services += @('payments', 'payments-event-publisher', 'orders-payment-consumer') }
    docker compose @config up -d --no-build --pull never --wait --wait-timeout 60 @services
    if ($LASTEXITCODE -ne 0) { throw 'Disposable Orders stack failed readiness.' }
    $integration = @()
    if ($WithCatalog) {
        if ($project -notmatch '^nivaro-orders-qa-[a-f0-9]{8}$') { throw 'Unsafe catalog fixture target.' }
        Get-Content "$PSScriptRoot/cart-browser-fixture.sql" -Raw | docker compose @config exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -d nivaro_catalog
        if ($LASTEXITCODE -ne 0) { throw 'Disposable catalog stock fixture failed.' }
        $integration = @('-e', 'ORDERS_CATALOG_E2E=1', '-v', "${root}/work/secrets/orders_client_secret.txt:/run/secrets/orders_client_secret:ro")
    }
    if ($WithEvents) {
        $integration += @('-e', 'ORDERS_EVENT_E2E=1',
            '-v', "${root}/work/secrets/catalog_db_password.txt:/run/secrets/catalog_db_password:ro",
            '-v', "${root}/work/secrets/catalog_event_broker_password.txt:/run/secrets/catalog_event_broker_password:ro")
    }
    if ($WithCheckout) { $integration += @('-e', 'ORDERS_CHECKOUT_E2E=1') }
    if ($WithPaymentResults) { $integration += @('-e', 'ORDERS_PAYMENT_E2E=1') }
    docker run --rm --pull never --network "${project}_default" -e "ORDERS_DB_HOST=$project-postgres-1" -e ORDERS_DISPOSABLE_TESTS=1 -e PYTHONPATH=/app/src -v "${root}/work/secrets/orders_db_password.txt:/run/secrets/orders_db_password:ro" -v "${root}/contracts/openapi/orders.json:/contracts/orders.json:ro" @integration $TestImage sh -ec 'alembic upgrade head && alembic check && ruff check . && ruff format --check . && mypy src && pytest -q && python -m nivaro_orders.export_openapi /contracts/orders.json --check'
    if ($LASTEXITCODE -ne 0) { throw 'Orders foundation checks failed.' }
    if ($WithEvents) {
        $expectedDeadLetters = @('orders.inventory.reservation.expired.v1')
        if ($WithPaymentResults) { $expectedDeadLetters += 'orders.payment.results.v1' }
        $deadLettered = $false
        foreach ($attempt in 1..10) {
            $queues = docker compose @config exec -T rabbitmq rabbitmqctl -q list_queues -p commerce-events name messages --formatter json | ConvertFrom-Json
            if ($LASTEXITCODE -ne 0) { throw 'Could not inspect disposable event queues.' }
            $drained = @($expectedDeadLetters | Where-Object {
                $queue = $_
                $dead = $queues | Where-Object name -EQ "$queue.error"
                $live = $queues | Where-Object name -EQ $queue
                $dead.messages -eq 1 -and $live.messages -eq 0
            })
            if ($drained.Count -eq $expectedDeadLetters.Count) { $deadLettered = $true; break }
            Start-Sleep -Seconds 1
        }
        if (-not $deadLettered) { throw 'Event queue did not drain into the expected dead-letter queue.' }
        Write-Output "RabbitMQ dead-letter routing verified for: $($expectedDeadLetters -join ', ')."
    }
    if ($Browser) {
        $env:TEST_BASE_URL = 'http://127.0.0.1:8082'
        $env:NIVARO_CHECKOUT_QA_PROJECT = $project
        Push-Location "$root/apps/web"
        try {
            node node_modules/@playwright/test/cli.js test tests/checkout-gateway.spec.ts
            if ($LASTEXITCODE -ne 0) { throw 'Checkout browser integration failed.' }
        } finally { Pop-Location }
    }
    Write-Output 'Orders release readiness, migrations, totals, coupon concurrency and reservation checks passed.'
} catch {
    if ($WithPaymentResults) { docker compose @config logs --no-color --tail 40 orders-payment-consumer payments-event-publisher payments }
    if ($WithEvents) {
        docker compose @config logs --no-color --tail 40 catalog-event-publisher orders-expiry-consumer rabbitmq
    }
    if ($WithCheckout) { docker compose @config logs --no-color --tail 40 orders gateway cart identity }
    throw
} finally {
    docker compose @config down --volumes
    $env:NIVARO_ORDERS_IMAGE = $previousImage
    $env:NIVARO_CART_QA_CATALOG_IMAGE = $previousCatalogImage
    $env:NIVARO_CART_QA_IDENTITY_IMAGE = $previousIdentityImage
    $env:NIVARO_EVENT_CATALOG_IMAGE = $previousPublisherImage
    $env:NIVARO_ORDERS_DELIVERY_RATES = $previousRates
    $env:NIVARO_QA_MOCK_PHONES = $previousPhones
    $env:NIVARO_CART_QA_WEB_IMAGE = $previousWebImage
    $env:TEST_BASE_URL = $previousBrowserUrl
    $env:NIVARO_CHECKOUT_QA_PROJECT = $previousBrowserProject
}
