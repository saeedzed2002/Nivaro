param(
    [string]$SupportImage = 'nivaro-support:release',
    [string]$TestImage = 'nivaro-support:test',
    [string]$IdentityImage = 'nivaro-identity:release'
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$project = 'nivaro-support-qa-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
$config = @('-p', $project, '--profile', 'support-replica', '-f', "$root/compose.yaml", '-f', "$root/compose.identity-qa.yaml", '-f', "$root/compose.cart-qa.yaml", '-f', "$root/compose.support.yaml", '-f', "$root/compose.support-qa.yaml")
$previousSupport = $env:NIVARO_SUPPORT_IMAGE
$previousIdentity = $env:NIVARO_CART_QA_IDENTITY_IMAGE
$previousOrigins = $env:SUPPORT_ALLOWED_ORIGINS
$previousRedisQA = $env:NIVARO_QA_SUPPORT_REDIS_PASSWORD
$testPassword = [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(24))
if ($project -notmatch '^nivaro-support-qa-[a-f0-9]{8}$') { throw 'Unsafe test project.' }

try {
    & "$PSScriptRoot/Initialize-LocalSecrets.ps1"
    $env:NIVARO_SUPPORT_IMAGE = $SupportImage
    $env:NIVARO_CART_QA_IDENTITY_IMAGE = $IdentityImage
    $env:SUPPORT_ALLOWED_ORIGINS = '["http://127.0.0.1:8082"]'
    $env:NIVARO_QA_SUPPORT_REDIS_PASSWORD = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
    docker compose @config up -d --no-build --pull never --wait --wait-timeout 85 support support-replica
    if ($LASTEXITCODE -ne 0) { throw 'Disposable support stack failed readiness.' }

    $seed = @'
import asyncio
import os

from nivaro_identity.infrastructure.database import Database
from nivaro_identity.infrastructure.models import Administrator, User
from nivaro_identity.main import passwords
from nivaro_identity.settings import Settings

async def seed():
    settings = Settings()
    assert settings.environment == 'test'
    database = Database(settings)
    password_hash = passwords.hash(os.environ['SUPPORT_TEST_PASSWORD'])
    try:
        async with database.sessions() as db, db.begin():
            for number, label, role in (
                (10, 'first', 'support_agent'), (11, 'second', 'support_agent'),
                (12, 'sales', 'sales_manager'), (13, 'manager', 'super_admin'),
            ):
                user = User(phone=f'+120255501{number:02d}')
                db.add(user)
                await db.flush()
                db.add(Administrator(user_id=user.id, email=f'{label}@example.com', password_hash=password_hash, role=role))
    finally:
        await database.engine.dispose()

asyncio.run(seed())
'@
    $seed | docker compose @config exec -T -e "SUPPORT_TEST_PASSWORD=$testPassword" identity python -
    if ($LASTEXITCODE -ne 0) { throw 'Support staff fixtures failed.' }

    docker run --rm --pull never --network "${project}_default" -e "SUPPORT_DB_HOST=$project-postgres-1" `
        -e SUPPORT_DISPOSABLE_TESTS=1 -e "SUPPORT_TEST_PASSWORD=$testPassword" -e NIVARO_QA_SUPPORT_REDIS_PASSWORD -e PYTHONPATH=/app/src `
        -v "${root}/work/secrets/support_db_password.txt:/run/secrets/support_db_password:ro" `
        -v "${root}/contracts/openapi/support.json:/contracts/support.json:ro" `
        -v "${root}/contracts/websocket:/contracts/websocket:ro" `
        $TestImage sh -ec 'alembic upgrade head && alembic check && ruff check . && ruff format --check . && mypy src && pytest -q && python -m nivaro_support.export_openapi /contracts/support.json --check && python -m nivaro_support.socket_contracts /contracts/websocket --check'
    if ($LASTEXITCODE -ne 0) { throw 'Support foundation checks failed.' }
    Write-Output 'Support migrations, private assignment, durable history, WebSocket and HTTP contract checks passed.'
} catch {
    docker compose @config logs --no-color --tail 25 support support-replica redis-support identity
    throw
} finally {
    docker compose @config down --volumes
    $env:NIVARO_SUPPORT_IMAGE = $previousSupport
    $env:NIVARO_CART_QA_IDENTITY_IMAGE = $previousIdentity
    $env:SUPPORT_ALLOWED_ORIGINS = $previousOrigins
    $env:NIVARO_QA_SUPPORT_REDIS_PASSWORD = $previousRedisQA
}
