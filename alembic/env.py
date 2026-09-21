"""Alembic environment for the Telos-X data database."""

import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import URL

from telos_x.models.database.telegram_db_model import (
    TelegramDataBaseDeclarativeBase,
)


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = TelegramDataBaseDeclarativeBase.metadata


def _configure_data_path() -> None:
    """Allow the DB location to come from data_path instead of a fixed URL."""
    arguments = context.get_x_argument(as_dictionary=True)
    data_path = arguments.get('data_path') or os.getenv('TELOSX_DATA_PATH')
    if not data_path:
        return

    database_path = Path(data_path).expanduser().resolve() / 'data_local.db'
    url = URL.create('sqlite', database=str(database_path)).render_as_string(
        hide_password=False
    )
    config.set_main_option('sqlalchemy.url', url.replace('%', '%%'))


def run_migrations_offline() -> None:
    """Run migrations without creating an Engine."""
    _configure_data_path()
    context.configure(
        url=config.get_main_option('sqlalchemy.url'),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={'paramstyle': 'named'},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against the configured Telos-X data DB."""
    _configure_data_path()
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix='sqlalchemy.',
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
