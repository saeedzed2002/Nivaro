from alembic import context
from sqlalchemy import create_engine, pool

from nivaro_identity.infrastructure.models import Base
from nivaro_identity.settings import Settings

config = context.config
target_metadata = Base.metadata

if context.is_offline_mode():
    context.configure(
        dialect_name="postgresql", target_metadata=target_metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(Settings().database_url(), poolclass=pool.NullPool, hide_parameters=True)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
