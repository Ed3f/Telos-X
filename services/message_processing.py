import json
import logging
from datetime import datetime
from typing import Dict, Optional

import pytz
from telethon import TelegramClient
from telethon.events import NewMessage
from telethon.tl.types import Channel, Message, PeerUser, User

from TEx.ai import TelosXAIAnalysis
from TEx.core.mapper.telethon_channel_mapper import TelethonChannelEntityMapper
from TEx.core.mapper.telethon_user_mapper import TelethonUserEntiyMapper
from TEx.core.media_handler import UniversalTelegramMediaHandler
from TEx.database.telegram_group_database import (
    TelegramGroupDatabaseManager,
    TelegramMessageDatabaseManager,
    TelegramUserDatabaseManager,
)
from TEx.database.telegram_message_ai_analysis_database import (
    TelegramMessageAIAnalysisDatabaseManager,
)
from TEx.finder.finder_engine import FinderEngine
from TEx.notifier.notifier_engine import NotifierEngine
from TEx.services.translation import TranslationService

logger = logging.getLogger("TelegramExplorer")


class MessageProcessingService:
    """
    Servizio unico di processamento messaggi per batch e realtime.

    Responsabilità:
    - costruzione payload raw del messaggio
    - download media opzionale
    - traduzione centralizzata
    - scelta del testo per AI
    - classificazione AI
    - esecuzione finder
    - esecuzione notifier
    - persistenza su telegram_message
    - persistenza su telegram_message_ai_analysis
    - sincronizzazione minima group/user se necessario
    """

    def __init__(self) -> None:
        self.media_handler = UniversalTelegramMediaHandler()
        self.finder = FinderEngine()
        self.notifier = NotifierEngine()
        self.ai_analysis = TelosXAIAnalysis()
        self.translation_service = TranslationService()
        self.is_configured = False

    def configure(self, config) -> None:
        """
        Configura i componenti che dipendono dal file di configurazione.
        """
        self.finder.configure(config=config)
        self.notifier.configure(config=config)
        self.is_configured = True

    async def process_message(
        self,
        *,
        message: Message,
        group_id: int,
        client: TelegramClient,
        data_path: str,
        download_media: bool,
        target_phone_number: str,
        pipeline: str,  # "batch" o "realtime"
        chat: Optional[Channel] = None,
        event: Optional[NewMessage.Event] = None,
    ) -> None:
        """
        Processa un singolo messaggio in modo uniforme per batch e realtime.

        Parametri:
        - message: messaggio Telethon
        - group_id: gruppo sorgente
        - client: TelegramClient
        - data_path: path dati del progetto
        - download_media: se True scarica media
        - target_phone_number: identificatore sorgente/account
        - pipeline: "batch" o "realtime"
        - chat/event: opzionali, utili per sincronizzazione live
        """

        if not self.is_configured:
            raise RuntimeError("MessageProcessingService.configure(config) must be called before process_message().")

        # Ignora messaggi totalmente vuoti e non utili
        raw_text: str = message.raw_text or ""
        message_text: str = message.message or raw_text or ""

        # 1. Assicurati che il gruppo esista nel DB
        await self._ensure_group_exists(
            group_id=group_id,
            target_phone_number=target_phone_number,
            client=client,
            chat=chat,
            event=event,
        )

        # 2. Assicurati che l'utente esista nel DB se identificabile
        from_id: Optional[int] = None
        from_type: Optional[str] = None

        if message.from_id is not None and isinstance(message.from_id, PeerUser):
            from_id = message.from_id.user_id
            from_type = "User"

            await self._ensure_user_exists(
                user_id=from_id,
                client=client,
                event=event,
            )

        # 3. Media opzionali
        media_id: Optional[int] = None
        if download_media:
            try:
                media_id = await self.media_handler.handle_medias(
                    message=message,
                    group_id=group_id,
                    data_path=data_path,
                )
            except Exception as exc:
                logger.error(
                    "[MEDIA ERROR] pipeline=%s group=%s msg=%s err=%s",
                    pipeline,
                    group_id,
                    message.id,
                    exc,
                )

        # 4. Traduzione centralizzata
        translation_result = await self.translation_service.translate(
            text=message_text,
            client=client,
            pipeline=pipeline,
            group_id=group_id,
            message_id=message.id,
        )

        translated_text = (
            translation_result.translated_text
            if translation_result.success and translation_result.translated_text
            else raw_text
        )

        # Questo è il testo usato per AI
        text_for_ai = translated_text if translated_text else raw_text

        # 5. Costruzione record raw coerente
        values: Dict = {
            "id": message.id,
            "group_id": group_id,
            "date_time": message.date.astimezone(tz=pytz.utc),
            "message": translated_text,
            "raw": raw_text,
            "to_id": getattr(message.to_id, "channel_id", None) if message.to_id is not None else None,
            "media_id": media_id,
            "from_id": from_id,
            "from_type": from_type,
            "is_reply": getattr(message, "is_reply", None),
            "reply_to_msg_id": (
                message.reply_to.reply_to_msg_id
                if getattr(message, "is_reply", False) and message.reply_to is not None
                else None
            ),
        }

        # 6. AI result di default
        ai_result = self._empty_ai_result()

        # 7. Classificazione AI
        if text_for_ai and text_for_ai.strip():
            try:
                ai_result = self.ai_analysis.analyze_message(text_for_ai)
                logger.info(
                    "[AI] pipeline=%s group=%s msg=%s activity=%s attack=%s nation=%s provider=%s",
                    pipeline,
                    group_id,
                    message.id,
                    ai_result["activity"]["top_label"],
                    ai_result["attack_type"]["top_label"],
                    ai_result["target_nation"]["top_label"],
                    translation_result.provider,
                )
            except Exception as exc:
                logger.error(
                    "[AI ERROR] pipeline=%s group=%s msg=%s err=%s",
                    pipeline,
                    group_id,
                    message.id,
                    exc,
                )

        # 8. Finder
        try:
            await self.finder.run(
                message=message,
                translation=translated_text,
                group_id=group_id,
                id=message.id,
            )
        except Exception as exc:
            logger.error(
                "[FINDER ERROR] pipeline=%s group=%s msg=%s err=%s",
                pipeline,
                group_id,
                message.id,
                exc,
            )

        # 9. Notifier standard
        try:
            await self.notifier.run(
                message=message,
                translation=translated_text,
                group_id=group_id,
                id=message.id,
                rule_id=None,
            )
        except Exception as exc:
            logger.error(
                "[NOTIFIER ERROR] pipeline=%s group=%s msg=%s err=%s",
                pipeline,
                group_id,
                message.id,
                exc,
            )

        # 10. Persistenza raw
        try:
            TelegramMessageDatabaseManager.insert(values)
        except Exception as exc:
            logger.error(
                "[DB MESSAGE ERROR] pipeline=%s group=%s msg=%s err=%s",
                pipeline,
                group_id,
                message.id,
                exc,
            )

        # 11. Persistenza AI enrichment
        try:
            TelegramMessageAIAnalysisDatabaseManager.insert({
                "message_id": message.id,
                "group_id": group_id,
                "activity_json": json.dumps(ai_result["activity"], ensure_ascii=False),
                "attack_type_json": json.dumps(ai_result["attack_type"], ensure_ascii=False),
                "target_nation_json": json.dumps(ai_result["target_nation"], ensure_ascii=False),
                "top_activity": ai_result["activity"]["top_label"],
                "top_activity_score": ai_result["activity"]["top_score"],
                "top_attack_type": ai_result["attack_type"]["top_label"],
                "top_attack_type_score": ai_result["attack_type"]["top_score"],
                "top_target_nation": ai_result["target_nation"]["top_label"],
                "top_target_nation_score": ai_result["target_nation"]["top_score"],
                "model_version": "lr_v1",
                "created_at": datetime.now(tz=pytz.UTC),
            })
        except Exception as exc:
            logger.error(
                "[DB AI ERROR] pipeline=%s group=%s msg=%s err=%s",
                pipeline,
                group_id,
                message.id,
                exc,
            )

    def _empty_ai_result(self) -> Dict:
        """
        Struttura AI standard di fallback.
        """
        return {
            "activity": {
                "labels": [],
                "scores": {},
                "top_label": None,
                "top_score": 0.0,
            },
            "attack_type": {
                "labels": [],
                "scores": {},
                "top_label": None,
                "top_score": 0.0,
            },
            "target_nation": {
                "labels": [],
                "scores": {},
                "top_label": None,
                "top_score": 0.0,
            },
        }

    async def _ensure_group_exists(
        self,
        *,
        group_id: int,
        target_phone_number: str,
        client: TelegramClient,
        chat: Optional[Channel],
        event: Optional[NewMessage.Event],
    ) -> None:
        """
        Garantisce che il gruppo esista nel DB.
        """
        if TelegramGroupDatabaseManager.get_by_id(pk=group_id):
            return

        logger.warning(
            'Group "%s" not found on DB. Performing automatic synchronization.',
            group_id,
        )

        result_chat = chat

        if result_chat is None and event is not None:
            try:
                result_chat = await event.get_chat()
            except Exception as exc:
                logger.error("[GROUP SYNC ERROR] group=%s err=%s", group_id, exc)
                return

        if result_chat is None:
            return

        try:
            group_dict_data: Dict = TelethonChannelEntityMapper.to_database_dict(
                entity=result_chat,
                target_phone_numer=target_phone_number,
            )
            TelegramGroupDatabaseManager.insert_or_update(group_dict_data)
        except Exception as exc:
            logger.error("[GROUP DB ERROR] group=%s err=%s", group_id, exc)

    async def _ensure_user_exists(
        self,
        *,
        user_id: int,
        client: TelegramClient,
        event: Optional[NewMessage.Event],
    ) -> None:
        """
        Garantisce che l'utente esista nel DB.
        """
        if TelegramUserDatabaseManager.get_by_id(pk=user_id):
            return

        logger.warning(
            'User "%s" not found on DB. Performing automatic synchronization.',
            user_id,
        )

        result_user: Optional[User] = None

        if event is not None:
            try:
                result_user = await event.get_sender()
            except Exception as exc:
                logger.error("[USER SYNC ERROR] user=%s err=%s", user_id, exc)
                return

        if result_user is None:
            return

        try:
            user_dict_data: Dict = TelethonUserEntiyMapper.to_database_dict(result_user)
            TelegramUserDatabaseManager.insert_or_update(user_dict_data)
        except Exception as exc:
            logger.error("[USER DB ERROR] user=%s err=%s", user_id, exc)