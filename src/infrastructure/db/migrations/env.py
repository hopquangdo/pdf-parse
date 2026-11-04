from alembic import context

from src.infrastructure.db.base import Base
from src.infrastructure.db import models  # noqa: F401  (registers the tables)

config = context.config
connection = config.attributes.get("connection")
if connection is None:  # `alembic` CLI use: build an engine from the app's own configuration
    from src.infrastructure.db.engine import get_engine

    connection = get_engine().connect()

context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
with context.begin_transaction():
    context.run_migrations()
