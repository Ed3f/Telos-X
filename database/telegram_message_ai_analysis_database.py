"""Telegram Message AI Analysis Database Manager."""
from typing import Dict, List, Optional, cast

import sqlalchemy.exc
from sqlalchemy import insert, select, desc
from sqlalchemy.orm import Session

from TELOSX.database.db_manager import DbManager
from TELOSX.models.database.telegram_db_model import TelegramMessageAIAnalysisOrmEntity


class TelegramMessageAIAnalysisDatabaseManager:
    """Telegram Message AI Analysis Database Manager."""

    @staticmethod
    def insert(entity_values: Dict) -> None:
        """Insert one Telegram Message AI Analysis record."""
        try:
            DbManager.SESSIONS['data'].execute(
                insert(TelegramMessageAIAnalysisOrmEntity).values(entity_values)
            )
            DbManager.SESSIONS['data'].commit()

        except sqlalchemy.exc.IntegrityError as exc:
            if 'UNIQUE' in exc.orig.args[0]:
                return
            raise exc

    @staticmethod
    def get_all_by_group(group_id: int) -> List[TelegramMessageAIAnalysisOrmEntity]:
        """Return all AI analysis rows for a group."""
        return cast(
            List[TelegramMessageAIAnalysisOrmEntity],
            DbManager.SESSIONS['data'].execute(
                select(TelegramMessageAIAnalysisOrmEntity)
                .where(TelegramMessageAIAnalysisOrmEntity.group_id == group_id)
                .order_by(desc(TelegramMessageAIAnalysisOrmEntity.created_at))
            ).scalars().all()
        )

    @staticmethod
    def get_by_message(message_id: int, group_id: int) -> Optional[TelegramMessageAIAnalysisOrmEntity]:
        """Return AI analysis row for one specific message."""
        return cast(
            Optional[TelegramMessageAIAnalysisOrmEntity],
            DbManager.SESSIONS['data'].execute(
                select(TelegramMessageAIAnalysisOrmEntity)
                .where(TelegramMessageAIAnalysisOrmEntity.message_id == message_id)
                .where(TelegramMessageAIAnalysisOrmEntity.group_id == group_id)
                .order_by(desc(TelegramMessageAIAnalysisOrmEntity.created_at))
                .limit(1)
            ).scalar_one_or_none()
        )