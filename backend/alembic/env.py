from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import get_settings
from app.core.db import Base
from app.models import *  # noqa: F401,F403  (ensures all models are registered on Base.metadata)

config = context.config
settings = get_settings()
# Read the DB URL straight from Settings rather than round-tripping it through
# alembic's ConfigParser-backed config object: ConfigParser treats "%" as its own
# interpolation syntax, which breaks on any password containing a percent-encoded
# character (e.g. "%40" for a literal "@") unless doubled to "%%". Bypassing
# set_main_option/get_main_option entirely avoids that footgun altogether.

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(settings.database_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
