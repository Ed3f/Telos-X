"""Telegram Group Database Manager."""
from typing import Dict, List, Optional, cast

import datetime

import pytz
import sqlalchemy.exc
from sqlalchemy import delete, desc, insert, select, text, update
from sqlalchemy.sql.expression import func
from sqlalchemy.engine import ChunkedIteratorResult, CursorResult, Row
from sqlalchemy.sql import Delete, Select, distinct, or_
from sqlalchemy.sql.elements import BinaryExpression
from sqlalchemy.orm import Session

from cachetools import cached

from telos_x.database import GROUPS_CACHE, USERS_CACHE
from telos_x.database.db_manager import DbManager
from telos_x.models.database.telegram_db_model import (
    TelegramGroupOrmEntity,
    TelegramMediaOrmEntity,
    TelegramMessageAIAnalysisOrmEntity,
    TelegramMessageOrmEntity,
    TelegramProfilePicOrmEntity,
    TelegramUserGroupOrmEntity,
    TelegramUserOrmEntity,
)


class TelegramGroupDatabaseManager:
    """Telegram Group Database Manager."""

    @staticmethod
    def get_all_by_phone_number(phone_number: str) -> List[TelegramGroupOrmEntity]:
        """Retrieve all Groups using the Source Phone Number."""
        return cast(
            List[TelegramGroupOrmEntity],
            DbManager.SESSIONS['data'].execute(
                select(TelegramGroupOrmEntity)
                .where(TelegramGroupOrmEntity.source == phone_number)
                ).scalars().all()
            )

    @staticmethod
    @cached(cache=GROUPS_CACHE)
    def get_by_id(pk: str) -> Optional[TelegramGroupOrmEntity]:
        """Retrieve one TelegramGroupOrmEntity by PK."""
        return cast(
            Optional[TelegramGroupOrmEntity],
            DbManager.SESSIONS['data'].get(TelegramGroupOrmEntity, pk)
            )

    @staticmethod
    def insert_or_update(entity_values: Dict) -> None:
        """Insert or Update one Telegram Group."""
        session: Session = DbManager.SESSIONS['data']
        try:
            entity = session.get(TelegramGroupOrmEntity, entity_values['id'])
            if entity is None:
                session.execute(insert(TelegramGroupOrmEntity).values(entity_values))
            else:
                session.execute(
                    update(TelegramGroupOrmEntity)
                    .where(TelegramGroupOrmEntity.id == entity_values['id'])
                    .values(entity_values)
                )
            session.commit()
            GROUPS_CACHE.clear()
        except Exception:
            session.rollback()
            raise


class TelegramMessageDatabaseManager:
    """Telegram Message Database Manager."""

    @staticmethod
    def get_all_messages_from_group(group_id: int, order_by_desc: bool = False, message_datetime_limit_seconds: Optional[int] = None) -> List[TelegramMessageOrmEntity]:
        """Return all Messages from a Single Group."""
        select_statement: Select = select(TelegramMessageOrmEntity).where(TelegramMessageOrmEntity.group_id == group_id)

        if message_datetime_limit_seconds:
            select_statement = select_statement.where(
                TelegramMessageOrmEntity.date_time >= (datetime.datetime.now(tz=pytz.UTC) - datetime.timedelta(seconds=message_datetime_limit_seconds))
                )

        if order_by_desc:
            select_statement = select_statement.order_by(desc('date_time'))

        return cast(
            List[TelegramMessageOrmEntity],
            DbManager.SESSIONS['data'].execute(select_statement).scalars().all()
            )

    @staticmethod
    def insert(entity_values: Dict) -> None:
        session = DbManager.SESSIONS["data"]

        try:
            session.execute(
                insert(
                    TelegramMessageOrmEntity
                ).values(entity_values)
            )

            session.commit()

        except sqlalchemy.exc.IntegrityError as exc:
            session.rollback()

            if "UNIQUE" in str(exc.orig):
                return

            raise

        except Exception:
            session.rollback()
            raise

    @staticmethod
    def get_max_id_from_group(group_id: int) -> Optional[int]:
        """Return the Maximum id from a Group (AKA: Last Offset)."""
        row: Optional[Row] = DbManager.SESSIONS['data'].execute(
            select(TelegramMessageOrmEntity)
            .where(TelegramMessageOrmEntity.group_id == group_id)
            .order_by(desc('id'))
            .limit(1)
            ).one_or_none()

        if row is None:
            return None

        return int(row[0].id)

    @staticmethod
    def count_messages_from_group(group_id: int, message_datetime_limit_seconds: Optional[int] = None) -> int:
        """Count all Messages from a Single Group."""
        select_statement: Select = select(TelegramMessageOrmEntity).where(TelegramMessageOrmEntity.group_id == group_id)

        if message_datetime_limit_seconds:
            select_statement = select_statement.where(
                TelegramMessageOrmEntity.date_time >= (datetime.datetime.now(tz=pytz.UTC) - datetime.timedelta(seconds=message_datetime_limit_seconds))
                )

        select_statement = select_statement.with_only_columns(func.count())  # pylint: disable=E1102

        return cast(int, DbManager.SESSIONS['data'].execute(select_statement).scalar())

    @staticmethod
    def count_active_users_from_group(group_id: int, message_datetime_limit_seconds: Optional[int] = None) -> int:
        """Count all Active Users from a Single Group."""
        select_statement: Select = select(TelegramMessageOrmEntity).where(TelegramMessageOrmEntity.group_id == group_id)

        if message_datetime_limit_seconds:
            select_statement = select_statement.where(
                TelegramMessageOrmEntity.date_time >= (datetime.datetime.now(tz=pytz.UTC) - datetime.timedelta(seconds=message_datetime_limit_seconds))
                )

        select_statement = select_statement.with_only_columns(func.count(distinct(TelegramMessageOrmEntity.from_id)))  # pylint: disable=E1102

        return cast(int, DbManager.SESSIONS['data'].execute(select_statement).scalar())

    @staticmethod
    def count_active_users(message_datetime_limit_seconds: Optional[int] = None) -> int:
        """Count all Users from a Single Group."""
        select_statement: Select = select(TelegramMessageOrmEntity).where(TelegramMessageOrmEntity.group_id > 0)

        if message_datetime_limit_seconds:
            select_statement = select_statement.where(
                TelegramMessageOrmEntity.date_time >= (datetime.datetime.now(tz=pytz.UTC) - datetime.timedelta(seconds=message_datetime_limit_seconds))
                )

        select_statement = select_statement.with_only_columns(func.count(distinct(TelegramMessageOrmEntity.from_id)))  # pylint: disable=E1102

        return cast(int, DbManager.SESSIONS['data'].execute(select_statement).scalar())

    @staticmethod
    def remove_all_messages_by_age(group_id: int, limit_days: int) -> int:
        """
        Remove all Messages older that Age in Seconds.

        :param group_id: Target Group ID
        :param limit_days: Age of Messages in Days
        :return: Number of Messages Removed
        """
        statement: Delete = delete(TelegramMessageOrmEntity)\
            .where(TelegramMessageOrmEntity.group_id == group_id)\
            .where(
                TelegramMessageOrmEntity.date_time <= (datetime.datetime.now(tz=pytz.UTC) - datetime.timedelta(days=limit_days))
                )

        session: Session = DbManager.SESSIONS['data']
        try:
            old_message_ids = select(TelegramMessageOrmEntity.id).where(
                TelegramMessageOrmEntity.group_id == group_id
            ).where(
                TelegramMessageOrmEntity.date_time
                <= (
                    datetime.datetime.now(tz=pytz.UTC)
                    - datetime.timedelta(days=limit_days)
                )
            )
            session.execute(
                delete(TelegramMessageAIAnalysisOrmEntity)
                .where(TelegramMessageAIAnalysisOrmEntity.group_id == group_id)
                .where(
                    TelegramMessageAIAnalysisOrmEntity.message_id.in_(
                        old_message_ids
                    )
                )
            )
            total_messages: int = cast(int, session.execute(statement).rowcount)
            session.commit()
            return total_messages
        except Exception:
            session.rollback()
            raise


class TelegramUserDatabaseManager:
    """Telegram User Database Manager."""

    @staticmethod
    @cached(cache=USERS_CACHE)
    def get_by_id(user_id: Optional[int]) -> Optional[TelegramUserOrmEntity]:
        """Retrieve one TelegramUserOrmEntity by PK."""
        if user_id is None:
            return None

        return cast(
            Optional[TelegramUserOrmEntity],
            DbManager.SESSIONS['data'].get(TelegramUserOrmEntity, user_id)
        )

    @staticmethod
    def get_user_by_id_group(group_id: Optional[int]) -> List[TelegramUserOrmEntity]:
        """Return all users observed in ``group_id`` (legacy public API)."""
        if group_id is None:
            return []
        return cast(
            List[TelegramUserOrmEntity],
            DbManager.SESSIONS['data'].execute(
                select(TelegramUserOrmEntity)
                .join(
                    TelegramUserGroupOrmEntity,
                    TelegramUserOrmEntity.id
                    == TelegramUserGroupOrmEntity.user_id,
                )
                .where(TelegramUserGroupOrmEntity.group_id == group_id)
            ).scalars().all()
        )

    @staticmethod
    def get_group_ids_by_user_id(user_id: int) -> List[int]:
        """Return every group in which a Telegram user was observed."""
        return cast(
            List[int],
            DbManager.SESSIONS['data'].execute(
                select(TelegramUserGroupOrmEntity.group_id)
                .where(TelegramUserGroupOrmEntity.user_id == user_id)
            ).scalars().all(),
        )

    @staticmethod
    def get_users_in_multiple_groups(
        minimum_groups: int = 2,
    ) -> List[TelegramUserOrmEntity]:
        """Return users observed in at least ``minimum_groups`` groups."""
        if minimum_groups < 1:
            raise ValueError("minimum_groups must be at least 1")

        return cast(
            List[TelegramUserOrmEntity],
            DbManager.SESSIONS['data'].execute(
                select(TelegramUserOrmEntity)
                .join(
                    TelegramUserGroupOrmEntity,
                    TelegramUserOrmEntity.id
                    == TelegramUserGroupOrmEntity.user_id,
                )
                .group_by(TelegramUserOrmEntity.id)
                .having(
                    func.count(TelegramUserGroupOrmEntity.group_id)
                    >= minimum_groups
                )
            ).scalars().all(),
        )

    @staticmethod
    def insert_or_update(values: Dict) -> None:
        """Insert or Update one Telegram User."""
        session: Session = DbManager.SESSIONS['data']
        try:
            TelegramUserDatabaseManager.__insert_or_update_single_entity(
                session,
                values,
            )
            session.commit()
            USERS_CACHE.clear()
        except Exception:
            session.rollback()
            raise

    @staticmethod
    def insert(entity_values: Dict) -> None:
        """Insert one Telegram user and its optional group association."""
        session: Session = DbManager.SESSIONS['data']
        try:
            user_values, group_id = TelegramUserDatabaseManager._split_user_and_group(
                entity_values
            )
            session.execute(insert(TelegramUserOrmEntity).values(user_values))
            TelegramUserDatabaseManager.__insert_user_group(
                session,
                user_values['id'],
                group_id,
            )
            session.commit()
            USERS_CACHE.clear()

        except sqlalchemy.exc.IntegrityError as exc:
            session.rollback()
            if 'UNIQUE' in str(exc.orig).upper():
                return

            raise
        except Exception:
            session.rollback()
            raise

    @staticmethod
    def insert_or_update_batch(values: Optional[List[Dict]]) -> None:
        """Insert or Update one Telegram User."""
        if values is None:
            return

        session: Session = DbManager.SESSIONS['data']
        associations_in_batch = set()
        try:
            for item in values:
                TelegramUserDatabaseManager.__insert_or_update_single_entity(
                    session,
                    item,
                    associations_in_batch,
                )
            session.commit()
            USERS_CACHE.clear()
        except Exception:
            session.rollback()
            raise

    @staticmethod
    def _split_user_and_group(entity_values: Dict) -> tuple[Dict, Optional[int]]:
        """Separate scraper-compatible ``group_id`` from user profile data."""
        user_values = dict(entity_values)
        group_id = user_values.pop('group_id', None)
        return user_values, group_id

    @staticmethod
    def __insert_or_update_single_entity(
        session: Session,
        entity_values: Dict,
        associations_in_batch: Optional[set] = None,
    ) -> None:
        """Insert or Update one Telegram User."""
        user_values, group_id = TelegramUserDatabaseManager._split_user_and_group(
            entity_values
        )
        user_id = user_values['id']
        entity = session.get(TelegramUserOrmEntity, user_id)

        if entity is None:
            session.execute(insert(TelegramUserOrmEntity).values(user_values))
        else:
            # Lightweight observations contain ``None`` for extended profile
            # fields.  Do not erase an already downloaded selective profile.
            update_values = {
                key: value
                for key, value in user_values.items()
                if key != 'id' and value is not None
            }
            if update_values:
                session.execute(
                    update(TelegramUserOrmEntity)
                    .where(TelegramUserOrmEntity.id == user_id)
                    .values(update_values)
                )

        TelegramUserDatabaseManager.__insert_user_group(
            session,
            user_id,
            group_id,
            associations_in_batch,
        )

    @staticmethod
    def __insert_user_group(
        session: Session,
        user_id: int,
        group_id: Optional[int],
        associations_in_batch: Optional[set] = None,
    ) -> None:
        """Insert a user/group pair once, relying on the composite PK."""
        if group_id is None:
            return

        key = (user_id, group_id)
        if associations_in_batch is not None and key in associations_in_batch:
            return
        if session.get(TelegramUserGroupOrmEntity, key) is not None:
            return

        session.add(
            TelegramUserGroupOrmEntity(
                user_id=user_id,
                group_id=group_id,
            )
        )
        if associations_in_batch is not None:
            associations_in_batch.add(key)


class TelegramProfilePicDatabaseManager: 
    
    @staticmethod
    @cached(cache=USERS_CACHE)
    def get_by_id(pk: Optional[int]) -> Optional[TelegramProfilePicOrmEntity]:
        """Retrieve one TelegramProfilePicOrmEntity by PK."""
        if pk is None:
            return None

        return cast(
            Optional[TelegramProfilePicOrmEntity],
            DbManager.SESSIONS['data'].get(TelegramProfilePicOrmEntity, pk)
            )
    
    @staticmethod
    def insert(entity_values: Dict) -> None:
        """Insert or Update one Telegram user."""
        session: Session = DbManager.SESSIONS['data']
        try:
            session.execute(
                insert(TelegramProfilePicOrmEntity).
                values(entity_values)
                )

            session.commit()

        except sqlalchemy.exc.IntegrityError as exc:
            session.rollback()
            if 'UNIQUE' in str(exc.orig).upper():
                return

            raise
        except Exception:
            session.rollback()
            raise

class TelegramMediaDatabaseManager:
    """Telegram Media Database Manager."""

    @staticmethod
    def get_by_id(pk: Optional[int]) -> Optional[TelegramMediaOrmEntity]:
        """Retrieve one TelegramUserOrmEntity by PK."""
        if pk is None:
            return None

        return cast(
            Optional[TelegramMediaOrmEntity],
            DbManager.SESSIONS['data'].get(TelegramMediaOrmEntity, pk)
            )

    @staticmethod
    def insert(entity_values: Dict) -> int:
        """Insert or Update one Telegram User."""
        session: Session = DbManager.SESSIONS['data']
        try:
            cursor: CursorResult = session.execute(
                insert(TelegramMediaOrmEntity).
                values(entity_values)
                )
            session.commit()
            return int(cursor.inserted_primary_key[0])
        except Exception:
            session.rollback()
            raise

    @staticmethod
    def get_all_medias_from_group_and_mimetype(group_id: int, mime_type: str, file_datetime_limit_seconds: Optional[int] = None, file_name_part: Optional[List[str]] = None) -> ChunkedIteratorResult:
        """
        Return all Messages from a Single Group.

        :param group_id: Target Group ID
        :param mime_type: Target Mime_Type
        :param file_datetime_limit_seconds: Age of File in Seconds
        :param file_name_part: Filter with Filename Part (Optional, use None for All Files)
        :return:
        """
        select_statement: Select = select(TelegramMediaOrmEntity)

        # File Age
        if file_datetime_limit_seconds:
            select_statement = select_statement.where(
                TelegramMediaOrmEntity.date_time >= (datetime.datetime.now(tz=pytz.UTC) - datetime.timedelta(seconds=file_datetime_limit_seconds))
                )

        # MimeType
        if mime_type and mime_type != '*':
            select_statement = select_statement.where(
                TelegramMediaOrmEntity.mime_type == mime_type
            )
        select_statement = select_statement.where(TelegramMediaOrmEntity.group_id == group_id)

        # Filename Filtering
        if file_name_part:
            parts_or_filter: List[BinaryExpression] = []

            for name_part in file_name_part:
                parts_or_filter.append(TelegramMediaOrmEntity.file_name.contains(name_part))

            select_statement = select_statement.where(or_(*parts_or_filter))

        return DbManager.SESSIONS['data'].execute(select_statement)

    @staticmethod
    def stats_all_medias_from_group_by_mimetype(group_id: int, file_datetime_limit_seconds: Optional[int] = None) -> Dict:
        """
        Generate Statistics of all Medias from a Single Group and Grouped by MimeType.

        :param group_id: Target Group ID
        :param file_datetime_limit_seconds: Age of File in Seconds
        :return: A List with Mime-Type, Number of Entries and Total Size in Bytes
        """
        select_statement: Select = select(TelegramMediaOrmEntity)

        # File Age
        if file_datetime_limit_seconds:
            select_statement = select_statement.where(
                TelegramMediaOrmEntity.date_time >= (datetime.datetime.now(tz=pytz.UTC) - datetime.timedelta(seconds=file_datetime_limit_seconds))
                )

        # Group Clause
        select_statement = select_statement.where(TelegramMediaOrmEntity.group_id == group_id)
        select_statement = select_statement.with_only_columns(
            distinct(TelegramMediaOrmEntity.mime_type),
            func.count(TelegramMediaOrmEntity.mime_type),  # pylint: disable=E1102
            func.sum(TelegramMediaOrmEntity.size_bytes)  # pylint: disable=E1102
            )
        select_statement = select_statement.group_by(TelegramMediaOrmEntity.mime_type)

        medias: ChunkedIteratorResult = DbManager.SESSIONS['data'].execute(select_statement).all()

        h_result: Dict = {}

        # Group Results
        for media in medias:
            h_result[media[0]] = {'count': media[1], 'size_bytes': media[2]}

        return h_result

    @staticmethod
    def get_all_medias_by_age(group_id: int, media_limit_days: int) -> List[TelegramMediaOrmEntity]:
        """
        Remove all Medias older that Age in Seconds.

        :param group_id: Target Group ID
        :param media_limit_days: Age of Media in Days
        :return: Number of Medias Removed
        """
        statement: Select = select(TelegramMediaOrmEntity).where(
            TelegramMediaOrmEntity.date_time <= (datetime.datetime.now(tz=pytz.UTC) - datetime.timedelta(days=media_limit_days))
            )

        statement = statement.where(TelegramMediaOrmEntity.group_id == group_id)

        return cast(
            List[TelegramMediaOrmEntity],
            DbManager.SESSIONS['data'].execute(statement).scalars().all()
            )

    @staticmethod
    def delete_media_by_id(media_id: int) -> None:
        """
        Remove Media by PK.

        :param group_id: Target Group ID
        :param media_id: Media ID
        :return:
        """
        statement: Delete = delete(TelegramMediaOrmEntity).where(TelegramMediaOrmEntity.id == media_id)
        session: Session = DbManager.SESSIONS['data']
        try:
            session.execute(statement)
            session.commit()
        except Exception:
            session.rollback()
            raise

    @staticmethod
    def apply_db_maintenance() -> None:
        """
        Remove all Medias older that Age in Seconds.

        :param group_id: Target Group ID
        :param file_datetime_limit_seconds: Age of File in Seconds
        :return: Number of Medias Removed
        """
        session: Session = DbManager.SESSIONS['data']
        try:
            session.commit()
            engine = DbManager.SQLALCHEMY_BINDS['data']
            with engine.connect().execution_options(
                isolation_level='AUTOCOMMIT'
            ) as connection:
                connection.exec_driver_sql('VACUUM')
        except Exception:
            session.rollback()
            raise
