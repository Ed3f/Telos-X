"""Tests for Telegram user/group persistence."""

import unittest

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

from telos_x.database import GROUPS_CACHE, USERS_CACHE
from telos_x.database.db_manager import DbManager
from telos_x.database.telegram_group_database import (
    TelegramGroupDatabaseManager,
    TelegramUserDatabaseManager,
)
from telos_x.models.database.telegram_db_model import (
    TelegramDataBaseDeclarativeBase,
    TelegramUserGroupOrmEntity,
    TelegramUserOrmEntity,
)


class TelegramUserGroupDatabaseTests(unittest.TestCase):
    """Exercise the many-to-many persistence API with SQLite FKs enabled."""

    def setUp(self) -> None:
        self.engine = create_engine('sqlite:///:memory:')

        @event.listens_for(self.engine, 'connect')
        def _enable_foreign_keys(dbapi_connection, _record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute('PRAGMA foreign_keys=ON')
            cursor.close()

        TelegramDataBaseDeclarativeBase.metadata.create_all(self.engine)
        self.session = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
        )()
        DbManager.SQLALCHEMY_BINDS = {'data': self.engine}
        DbManager.SESSIONS = {'data': self.session}
        GROUPS_CACHE.clear()
        USERS_CACHE.clear()

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()
        GROUPS_CACHE.clear()
        USERS_CACHE.clear()

    @staticmethod
    def _group(group_id: int) -> dict:
        return {
            'id': group_id,
            'constructor_id': '1',
            'access_hash': 'hash',
            'group_username': f'group_{group_id}',
            'title': f'Group {group_id}',
            'fake': False,
            'gigagroup': False,
            'has_geo': False,
            'restricted': False,
            'scam': False,
            'verified': False,
            'participants_count': 1,
            'photo_id': None,
            'photo_base64': None,
            'photo_name': None,
            'source': 'test',
        }

    @staticmethod
    def _user(user_id: int, group_id: int, **overrides) -> dict:
        values = {
            'id': user_id,
            'username': f'user_{user_id}',
            'first_name': 'Test',
            'last_name': 'User',
            'phone_number': None,
            'is_bot': False,
            'is_fake': False,
            'is_self': False,
            'is_scam': False,
            'is_verified': False,
            'photo_id': None,
            'photo_base64': None,
            'photo_name': None,
            'date_profilation': None,
            'bio': None,
            'group_id': group_id,
        }
        values.update(overrides)
        return values

    def _insert_groups(self, *group_ids: int) -> None:
        for group_id in group_ids:
            TelegramGroupDatabaseManager.insert_or_update(self._group(group_id))

    def test_bridge_has_only_composite_primary_key(self) -> None:
        table = TelegramUserGroupOrmEntity.__table__
        self.assertEqual(
            {'user_id', 'group_id'},
            {column.name for column in table.primary_key.columns},
        )
        self.assertNotIn('id', table.columns)

    def test_same_user_in_multiple_groups_without_duplicates(self) -> None:
        self._insert_groups(10, 20, 30)
        TelegramUserDatabaseManager.insert_or_update_batch(
            [
                self._user(123, 10),
                self._user(123, 20),
                self._user(123, 30),
            ]
        )

        user_count = self.session.scalar(
            select(func.count()).select_from(TelegramUserOrmEntity)
        )
        association_count = self.session.scalar(
            select(func.count()).select_from(TelegramUserGroupOrmEntity)
        )
        self.assertEqual(1, user_count)
        self.assertEqual(3, association_count)

        TelegramUserDatabaseManager.insert_or_update(self._user(123, 20))
        association_count = self.session.scalar(
            select(func.count()).select_from(TelegramUserGroupOrmEntity)
        )
        self.assertEqual(3, association_count)

        self.assertEqual(
            [123],
            [user.id for user in TelegramUserDatabaseManager.get_user_by_id_group(20)],
        )
        self.assertEqual(
            {10, 20, 30},
            set(TelegramUserDatabaseManager.get_group_ids_by_user_id(123)),
        )
        self.assertEqual(
            [123],
            [
                user.id
                for user in TelegramUserDatabaseManager.get_users_in_multiple_groups(3)
            ],
        )

    def test_light_observation_does_not_erase_extended_profile(self) -> None:
        self._insert_groups(10, 20)
        TelegramUserDatabaseManager.insert_or_update(
            self._user(123, 10, bio='extended bio', photo_base64='encoded')
        )
        TelegramUserDatabaseManager.insert_or_update(self._user(123, 20))

        user = TelegramUserDatabaseManager.get_by_id(123)
        self.assertIsNotNone(user)
        self.assertEqual('extended bio', user.bio)
        self.assertEqual('encoded', user.photo_base64)

    def test_batch_rolls_back_completely_and_session_remains_usable(self) -> None:
        self._insert_groups(10)
        with self.assertRaises(Exception):
            TelegramUserDatabaseManager.insert_or_update_batch(
                [
                    self._user(123, 10),
                    self._user(456, 999),
                ]
            )

        self.assertEqual(
            0,
            self.session.scalar(
                select(func.count()).select_from(TelegramUserOrmEntity)
            ),
        )
        self.assertEqual(
            0,
            self.session.scalar(
                select(func.count()).select_from(TelegramUserGroupOrmEntity)
            ),
        )
        # A query after the failed commit proves rollback restored the session.
        self.assertEqual(1, self.session.scalar(select(func.count())))


if __name__ == '__main__':
    unittest.main()
