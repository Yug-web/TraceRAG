from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import Settings
from app.models import embedding  # noqa: F401 — register embedding tables in metadata
from app.models.document import Base

url = context.config.attributes.get("database_url")
if url is None:
    settings = Settings()
    if settings.database_url is None:
        raise RuntimeError("Set TRACERAG_DATABASE_URL before running migrations")
    url = settings.database_url.get_secret_value()

if context.is_offline_mode():
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(
        url, poolclass=pool.NullPool, hide_parameters=True, connect_args={"connect_timeout": 5}
    )
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
