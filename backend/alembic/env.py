from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from ccas.storage.models import Base

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers defaults to True, which would set ``.disabled =
    # True`` on every logger not named in alembic.ini's [loggers] section
    # (e.g. ``ccas.ingestor.job``). When migrations run inside a pytest session
    # (the Alembic up/down/up tests call command.upgrade()), that silences
    # application loggers for the rest of the session and breaks later tests
    # that assert on log propagation via caplog. Keep existing loggers intact.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _get_sync_url() -> str:
    """Convert async URL to sync for Alembic migrations."""
    from ccas.config import get_settings

    url = get_settings().database_url
    return url.replace("sqlite+aiosqlite:", "sqlite:")


def run_migrations_offline() -> None:
    url = _get_sync_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _get_sync_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
