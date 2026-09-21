"""Database Manager."""

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker


class DbManager:
    """Main Database Manager."""

    SQLALCHEMY_BINDS = {}  # type:ignore
    SESSIONS = {}  # type:ignore

    @staticmethod
    def init_db(data_path: str) -> None:
        """Initialize the DB Connection."""
        database_directory = Path(data_path).expanduser().resolve()
        database_directory.mkdir(parents=True, exist_ok=True)
        data_engine = create_engine(
            f'sqlite:///{database_directory / "data_local.db"}',
            connect_args={'check_same_thread': False},
            echo=False,
            logging_name='sqlalchemy',
            isolation_level='READ UNCOMMITTED',
        )
        DbManager._enable_sqlite_foreign_keys(data_engine)

        DbManager.SQLALCHEMY_BINDS = {
            'temp': create_engine(
                f'sqlite:///{database_directory / "temp_local.db"}',
                connect_args={'check_same_thread': False},
                echo=False, logging_name='sqlalchemy', isolation_level='READ UNCOMMITTED'
                ),
            'data': data_engine,
            }

        DbManager.SESSIONS = {
            'temp': sessionmaker(autocommit=False, autoflush=False, bind=DbManager.SQLALCHEMY_BINDS['temp'])(),
            'data': sessionmaker(autocommit=False, autoflush=False, bind=DbManager.SQLALCHEMY_BINDS['data'])()
            }

    @staticmethod
    def _enable_sqlite_foreign_keys(engine: Engine) -> None:
        """Enable SQLite FK enforcement for every data DB connection."""

        @event.listens_for(engine, 'connect')
        def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute('PRAGMA foreign_keys=ON')
            finally:
                cursor.close()
