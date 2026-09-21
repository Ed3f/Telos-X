"""Shared isolated database fixtures for Telos-X tests."""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from telos_x.database import GROUPS_CACHE, USERS_CACHE
from telos_x.database.db_manager import DbManager
from telos_x.models.database.telegram_db_model import TelegramDataBaseDeclarativeBase
from telos_x.models.database.temp_db_models import TempDataBaseDeclarativeBase


@pytest.fixture
def database(tmp_path):
    """Bind all managers to temporary SQLite databases with FKs enabled."""
    data_engine = create_engine(f"sqlite:///{tmp_path / 'data.db'}")
    temp_engine = create_engine(f"sqlite:///{tmp_path / 'temp.db'}")

    @event.listens_for(data_engine, 'connect')
    def _foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.close()

    TelegramDataBaseDeclarativeBase.metadata.create_all(data_engine)
    TempDataBaseDeclarativeBase.metadata.create_all(temp_engine)
    data_session = sessionmaker(bind=data_engine, autoflush=False)()
    temp_session = sessionmaker(bind=temp_engine, autoflush=False)()
    DbManager.SQLALCHEMY_BINDS = {'data': data_engine, 'temp': temp_engine}
    DbManager.SESSIONS = {'data': data_session, 'temp': temp_session}
    GROUPS_CACHE.clear()
    USERS_CACHE.clear()
    yield data_session
    data_session.close()
    temp_session.close()
    data_engine.dispose()
    temp_engine.dispose()
    GROUPS_CACHE.clear()
    USERS_CACHE.clear()


@pytest.fixture
def group_values():
    def _values(group_id=100, source='+1000', title=None):
        return {
            'id': group_id,
            'constructor_id': '1',
            'access_hash': 'hash',
            'group_username': f'group_{group_id}',
            'title': title or f'Group {group_id}',
            'fake': False,
            'gigagroup': False,
            'has_geo': False,
            'restricted': False,
            'scam': False,
            'verified': False,
            'participants_count': 0,
            'photo_id': None,
            'photo_base64': None,
            'photo_name': None,
            'source': source,
        }
    return _values


@pytest.fixture
def user_values():
    def _values(user_id, group_id, username=None):
        return {
            'id': user_id,
            'username': username or f'user_{user_id}',
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
    return _values
