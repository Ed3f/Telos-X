"""Integration test for the non-destructive user/group Alembic migration."""

import tempfile
import unittest
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


class TelegramUserGroupMigrationTests(unittest.TestCase):
    """Migrate an old SQLite schema and verify membership backfill."""

    def test_upgrade_backfills_valid_membership_and_drops_old_column(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / 'data_local.db'
            engine = create_engine(f'sqlite:///{database_path}')
            with engine.begin() as connection:
                connection.execute(
                    text('CREATE TABLE telegram_group (id INTEGER PRIMARY KEY)')
                )
                connection.execute(
                    text(
                        'CREATE TABLE telegram_user ('
                        'id INTEGER PRIMARY KEY, username TEXT, '
                        'date_profilation DATETIME NOT NULL, group_id INTEGER)'
                    )
                )
                connection.execute(
                    text('INSERT INTO telegram_group (id) VALUES (10), (20)')
                )
                connection.execute(
                    text(
                        "INSERT INTO telegram_user "
                        "(id, username, date_profilation, group_id) "
                        "VALUES (123, 'valid', CURRENT_TIMESTAMP, 20), "
                        "(456, 'orphan', CURRENT_TIMESTAMP, 999)"
                    )
                )
            engine.dispose()

            project_root = Path(__file__).resolve().parents[1]
            alembic_config = Config(str(project_root / 'alembic.ini'))
            alembic_config.set_main_option(
                'script_location',
                str(project_root / 'alembic'),
            )
            alembic_config.set_main_option(
                'sqlalchemy.url',
                f'sqlite:///{database_path}',
            )
            command.upgrade(alembic_config, 'head')

            engine = create_engine(f'sqlite:///{database_path}')
            with engine.connect() as connection:
                user_columns = {
                    column['name']
                    for column in inspect(connection).get_columns('telegram_user')
                }
                profiling_column = next(
                    column
                    for column in inspect(connection).get_columns('telegram_user')
                    if column['name'] == 'date_profilation'
                )
                memberships = connection.execute(
                    text(
                        'SELECT user_id, group_id FROM telegram_user_group '
                        'ORDER BY user_id, group_id'
                    )
                ).all()
                primary_key = inspect(connection).get_pk_constraint(
                    'telegram_user_group'
                )['constrained_columns']
            engine.dispose()

            self.assertNotIn('group_id', user_columns)
            self.assertTrue(profiling_column['nullable'])
            self.assertEqual([(123, 20)], memberships)
            self.assertEqual({'user_id', 'group_id'}, set(primary_key))


if __name__ == '__main__':
    unittest.main()
