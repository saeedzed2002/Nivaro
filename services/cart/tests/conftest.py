import os

import pytest

from nivaro_cart.infrastructure.database import Database
from nivaro_cart.settings import Settings


@pytest.fixture
async def database():
    settings = Settings()
    if os.getenv("CART_DISPOSABLE_TESTS") != "1":
        pytest.skip("Disposable database required")
    assert settings.db_host.startswith("nivaro-cart-pg-")
    instance = Database(settings)
    yield instance
    await instance.engine.dispose()
