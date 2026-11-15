param(
    [string]$PaymentsImage = 'nivaro-payments:release',
    [string]$TestImage = 'nivaro-payments:test',
    [string]$IdentityImage = 'nivaro-identity:release',
    [switch]$WithEvents
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$project = 'nivaro-payments-qa-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
if ($project -notmatch '^nivaro-payments-qa-[a-f0-9]{8}$') { throw 'Invalid disposable Payments project.' }
$config = @('-p', $project, '-f', "$root/compose.yaml", '-f', "$root/compose.identity-qa.yaml", '-f', "$root/compose.cart-qa.yaml", '-f', "$root/compose.payments.yaml")
$previousImage = $env:NIVARO_PAYMENTS_IMAGE
$previousIdentity = $env:NIVARO_CART_QA_IDENTITY_IMAGE
$services = @('payments', 'gateway')
$eventTest = @()
if ($WithEvents) {
    $config += @('-f', "$root/compose.media.yaml", '-f', "$root/compose.payment-events.yaml")
    $services += 'rabbitmq'
    $eventTest = @('-e', 'PAYMENTS_EVENT_E2E=1',
        '-v', "${root}/work/secrets/payments_event_broker_password.txt:/run/secrets/payments_event_broker_password:ro",
        '-v', "${root}/work/secrets/catalog_event_broker_password.txt:/run/secrets/catalog_event_broker_password:ro")
}

function Count-PendingPaymentEvents {
    $count = docker compose @config exec -T postgres psql -Atq -v ON_ERROR_STOP=1 -U postgres -d nivaro_payments -c 'SELECT count(*) FROM event_outbox WHERE published_at IS NULL AND failed_at IS NULL;'
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect pending payment events.' }
    return [int]$count
}

try {
    & "$PSScriptRoot/Initialize-LocalSecrets.ps1"
    if ($WithEvents) { & "$PSScriptRoot/Initialize-MediaSecrets.ps1" }
    $env:NIVARO_PAYMENTS_IMAGE = $PaymentsImage
    $env:NIVARO_CART_QA_IDENTITY_IMAGE = $IdentityImage
    docker compose @config up -d --no-build --pull never --wait --wait-timeout 90 @services
    if ($LASTEXITCODE -ne 0) { throw 'Disposable Payments stack failed readiness.' }
    docker run --rm --pull never --network "${project}_default" `
        -e "PAYMENTS_DB_HOST=$project-postgres-1" -e PAYMENTS_E2E=1 -e PYTHONPATH=/app/src `
        -v "${root}/work/secrets/payments_db_password.txt:/run/secrets/payments_db_password:ro" `
        -v "${root}/work/secrets/orders_client_secret.txt:/run/secrets/orders_client_secret:ro" `
        @eventTest $TestImage sh -ec 'alembic upgrade head && alembic check && ruff check . && ruff format --check . && mypy src && pytest -q'
    if ($LASTEXITCODE -ne 0) { throw 'Payments foundation checks failed.' }
    if ($WithEvents) {
        $pending = Count-PendingPaymentEvents
        if ($pending -lt 4) { throw 'The test did not leave payment outcomes to publish.' }
        docker compose @config stop rabbitmq
        if ($LASTEXITCODE -ne 0) { throw 'Could not stop the disposable payment broker.' }
        docker compose @config up -d --no-build --pull never --no-deps payments-event-publisher
        if ($LASTEXITCODE -ne 0) { throw 'Could not start the publisher against the stopped broker.' }
        $observedOutage = $false
        foreach ($attempt in 1..12) {
            $publisherLog = docker compose @config logs --no-color --tail 15 payments-event-publisher
            if ($LASTEXITCODE -ne 0) { throw 'Could not inspect the payment publisher.' }
            if ($publisherLog -match 'Payments event broker is unavailable') { $observedOutage = $true; break }
            Start-Sleep -Seconds 1
        }
        if (-not $observedOutage -or (Count-PendingPaymentEvents) -ne $pending) { throw 'Payment outbox did not survive the broker outage.' }

        docker compose @config up -d --no-build --pull never --no-deps --wait --wait-timeout 45 rabbitmq
        if ($LASTEXITCODE -ne 0) { throw 'Could not restart the disposable payment broker.' }
        $drained = $false
        foreach ($attempt in 1..24) {
            if ((Count-PendingPaymentEvents) -eq 0) { $drained = $true; break }
            Start-Sleep -Seconds 1
        }
        if (-not $drained) { throw 'The payment outbox did not drain after broker recovery.' }
        $paymentQueue = $null
        foreach ($attempt in 1..10) {
            $queues = docker compose @config exec -T rabbitmq rabbitmqctl -q list_queues -p commerce-events name type messages --formatter json | ConvertFrom-Json
            if ($LASTEXITCODE -ne 0) { throw 'Could not read payment queue metrics.' }
            $paymentQueue = $queues | Where-Object name -EQ 'orders.payment.results.v1'
            if ($paymentQueue.type -eq 'quorum' -and $paymentQueue.messages -eq $pending) { break }
            Start-Sleep -Seconds 1
        }
        if ($paymentQueue.type -ne 'quorum' -or $paymentQueue.messages -ne $pending) {
            throw "Expected $pending events in the quorum payment queue. Observed type '$($paymentQueue.type)' and count '$($paymentQueue.messages)'."
        }
        Write-Output "Payment publisher recovered after the broker outage. The durable Orders queue retained $pending events."
    }
    Write-Output 'Verified payment simulation, service scope, database isolation and concurrent idempotency.'
} catch {
    docker compose @config logs --no-color --tail 35 payments identity gateway
    if ($WithEvents) { docker compose @config logs --no-color --tail 25 payments-event-publisher rabbitmq }
    throw
} finally {
    docker compose @config down --volumes
    $env:NIVARO_PAYMENTS_IMAGE = $previousImage
    $env:NIVARO_CART_QA_IDENTITY_IMAGE = $previousIdentity
}
