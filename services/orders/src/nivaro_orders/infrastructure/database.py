from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from nivaro_orders.settings import Settings


class Database:
    def __init__(self, settings: Settings):
        self.engine = create_async_engine(
            settings.database_url(),
            pool_pre_ping=True,
            pool_size=settings.db_pool_size,
            max_overflow=0,
            pool_timeout=5,
            connect_args={"connect_timeout": 5, "options": "-c statement_timeout=5000"},
            hide_parameters=True,
        )
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
