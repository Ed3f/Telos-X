from __future__ import annotations

import asyncio
import datetime
import json
import logging
from configparser import ConfigParser
from typing import Any, Dict, List, Optional

from telethon.tl.types import Message

from telos_x.ai.telosx_ai_analysis import TelosXAIAnalysis
from telos_x.core.media_handler import UniversalTelegramMediaHandler
from telos_x.database.telegram_group_database import (
    TelegramMessageDatabaseManager,
)
from telos_x.database.telegram_message_ai_analysis_database import (
    TelegramMessageAIAnalysisDatabaseManager,
)
from telos_x.finder.finder_engine import FinderEngine
from telos_x.notifier.notifier_engine import NotifierEngine
from telos_x.paths import resolve_project_path

# Nel progetto attuale la cartella si chiama ancora "traslation".
from telos_x.services.traslation.translation_service import TranslationService


logger = logging.getLogger("TelegramExplorer")


class MessageProcessingService:
    """
    Pipeline condivisa da scraper batch e listener realtime.

    Flusso:

        Telegram Message
            ↓
        Media handling
            ↓
        TranslationService
            ↓
        salvataggio messaggio raw
            ↓
        Finder signals
            ↓
        LR classification
            ↓
        DecisionEngine
            ↓
        BERT opzionale
            ↓
        Risk scoring
            ↓
        salvataggio analisi AI
            ↓
        notifiche
    """

    def __init__(self) -> None:
        self.config: Optional[ConfigParser] = None

        self.finder = FinderEngine()
        self.notifier = NotifierEngine()
        self.media_handler = UniversalTelegramMediaHandler()

        # Inizializzazione ritardata.
        #
        # Se traduzione locale o modelli AI non sono disponibili,
        # il salvataggio RAW dei messaggi deve continuare comunque.
        self.translation_service: Optional[TranslationService] = None
        self.ai_analysis: Optional[TelosXAIAnalysis] = None

        self.ai_enabled: bool = True
        self.translation_enabled: bool = True

        self.model_version: str = "lr_bert_v2"

    def configure(
        self,
        config: ConfigParser,
    ) -> None:
        """
        Configura tutti i componenti condivisi della pipeline.
        """

        self.config = config

        # ---------------------------------------------------------
        # Finder / notifier
        # ---------------------------------------------------------

        self.finder.configure(config)
        self.notifier.configure(config)

        # ---------------------------------------------------------
        # Configurazione generale
        # ---------------------------------------------------------

        self.ai_enabled = config.getboolean(
            "AI",
            "enabled",
            fallback=True,
        )

        self.translation_enabled = config.getboolean(
            "TRANSLATION",
            "enabled",
            fallback=True,
        )

        self.model_version = config.get(
            "AI",
            "model_version",
            fallback="lr_bert_v2",
        )

        # ---------------------------------------------------------
        # TranslationService
        # ---------------------------------------------------------

        # Reset esplicito nel caso configure() venga richiamato
        # più di una volta.
        self.translation_service = None

        if self.translation_enabled:
            try:
                self.translation_service = TranslationService(
                    model_path=str(
                        resolve_project_path(
                            config.get(
                                "TRANSLATION",
                                "model_path",
                                fallback=(
                                    "models/"
                                    "nllb-200-distilled-600M-ct2"
                                ),
                            )
                        )
                    ),
                    tokenizer_name=config.get(
                        "TRANSLATION",
                        "tokenizer_name",
                        fallback=(
                            "facebook/"
                            "nllb-200-distilled-600M"
                        ),
                    ),
                    device=config.get(
                        "TRANSLATION",
                        "device",
                        fallback="cpu",
                    ),
                    compute_type=config.get(
                        "TRANSLATION",
                        "compute_type",
                        fallback="int8",
                    ),
                    inter_threads=config.getint(
                        "TRANSLATION",
                        "inter_threads",
                        fallback=1,
                    ),
                    intra_threads=config.getint(
                        "TRANSLATION",
                        "intra_threads",
                        fallback=0,
                    ),
                    beam_size=config.getint(
                        "TRANSLATION",
                        "beam_size",
                        fallback=4,
                    ),
                    max_decoding_length=config.getint(
                        "TRANSLATION",
                        "max_decoding_length",
                        fallback=256,
                    ),
                )

                logger.info(
                    "[MESSAGE PROCESSING] "
                    "TranslationService inizializzato."
                )

            except Exception:
                self.translation_service = None

                logger.exception(
                    "[MESSAGE PROCESSING] "
                    "Impossibile inizializzare TranslationService. "
                    "Verrà utilizzato il testo originale."
                )

        else:
            logger.info(
                "[MESSAGE PROCESSING] "
                "Traduzione disabilitata da configurazione."
            )

        # ---------------------------------------------------------
        # AI
        # ---------------------------------------------------------

        self.ai_analysis = None

        if self.ai_enabled:
            try:
                self.ai_analysis = TelosXAIAnalysis()

                logger.info(
                    "[MESSAGE PROCESSING] "
                    "TelosXAIAnalysis inizializzato."
                )

            except Exception:
                self.ai_analysis = None

                logger.exception(
                    "[MESSAGE PROCESSING] "
                    "Impossibile inizializzare TelosXAIAnalysis. "
                    "I messaggi RAW continueranno comunque "
                    "a essere salvati."
                )

        else:
            logger.info(
                "[MESSAGE PROCESSING] "
                "Analisi AI disabilitata da configurazione."
            )

    async def process_message(
        self,
        *,
        message: Message,
        group_id: int,
        client: Any,
        data_path: str,
        download_media: bool,
        target_phone_number: str,
        pipeline: str,
        chat: Any = None,
        event: Any = None,
    ) -> Dict[str, Any]:
        """
        Elabora un singolo messaggio Telegram.

        Errori di:
        - media;
        - traduzione;
        - Finder;
        - AI;
        - database;
        - notifier;

        non devono interrompere l'intera pipeline.
        """

        # Attualmente mantenuti nella firma per compatibilità
        # con batch scraper e listener.
        del target_phone_number
        del pipeline
        del event

        raw_text = self._extract_raw_text(
            message
        )

        translated_text = raw_text

        media_id: Optional[int] = None

        # ---------------------------------------------------------
        # Compatibilità message.chat nel batch scraper
        # ---------------------------------------------------------

        # Alcuni notifier accedono direttamente a message.chat.
        #
        # Nel listener Telethon normalmente lo valorizza.
        # Nel batch scraper può invece essere assente.
        if (
            chat is not None
            and getattr(
                message,
                "chat",
                None,
            )
            is None
        ):
            try:
                message._chat = chat  # type: ignore[attr-defined]

            except Exception:
                logger.debug(
                    "[MESSAGE PROCESSING] "
                    "Impossibile assegnare message._chat.",
                    exc_info=True,
                )

        # =========================================================
        # 1. MEDIA
        # =========================================================

        if download_media:
            try:
                media_id = (
                    await self.media_handler.handle_medias(
                        message=message,
                        group_id=group_id,
                        data_path=data_path,
                    )
                )

            except Exception:
                logger.exception(
                    "[MESSAGE PROCESSING] "
                    "Errore durante la gestione del media "
                    "del messaggio %s nel gruppo %s.",
                    message.id,
                    group_id,
                )

        # =========================================================
        # 2. TRADUZIONE
        # =========================================================

        if (
            self.translation_enabled
            and self.translation_service is not None
            and raw_text.strip()
        ):
            try:
                translation_result = (
                    await self.translation_service.translate(
                        text=raw_text,

                        # Il TelegramTranslationProvider usa
                        # il client Telethon.
                        client=client,

                        # Mantenuti disponibili per eventuali
                        # provider futuri.
                        message=message,
                        group_id=group_id,
                    )
                )

                if (
                    translation_result.success
                    and translation_result.translated_text
                ):
                    translated_text = (
                        translation_result.translated_text
                    )

                    logger.debug(
                        "[MESSAGE PROCESSING] "
                        "Messaggio %s tradotto con provider %s.",
                        message.id,
                        translation_result.provider,
                    )

                else:
                    translated_text = raw_text

                    logger.warning(
                        "[MESSAGE PROCESSING] "
                        "Traduzione non disponibile per il messaggio %s. "
                        "Provider=%s Error=%s. "
                        "Uso del testo originale.",
                        message.id,
                        translation_result.provider,
                        translation_result.error,
                    )

            except Exception:
                translated_text = raw_text

                logger.exception(
                    "[MESSAGE PROCESSING] "
                    "Errore di traduzione per il messaggio %s "
                    "nel gruppo %s. "
                    "Verrà utilizzato il testo originale.",
                    message.id,
                    group_id,
                )

        # =========================================================
        # 3. PERSISTENZA RAW
        # =========================================================

        raw_values = self._build_raw_message_values(
            message=message,
            group_id=group_id,
            media_id=media_id,
            raw_text=raw_text,
            translated_text=translated_text,
        )

        raw_saved = False

        try:
            TelegramMessageDatabaseManager.insert(
                entity_values=raw_values,
            )

            raw_saved = True

        except Exception:
            logger.exception(
                "[MESSAGE PROCESSING] "
                "Errore nel salvataggio RAW del messaggio %s "
                "nel gruppo %s.",
                message.id,
                group_id,
            )

        # =========================================================
        # 4. FINDER / CTI SIGNALS
        # =========================================================

        signal_hits: List[
            Dict[str, Any]
        ] = []

        try:
            signal_hits = (
                await self.finder.find_signals(
                    message=message,
                    translation=translated_text,
                    raw_text=raw_text,
                    group_id=group_id,
                    id=message.id,
                )
            )

        except Exception:
            logger.exception(
                "[MESSAGE PROCESSING] "
                "Finder fallito sul messaggio %s "
                "nel gruppo %s.",
                message.id,
                group_id,
            )

        # =========================================================
        # 5. ANALISI AI
        # =========================================================

        ai_result = self._empty_ai_result()

        if (
            self.ai_enabled
            and self.ai_analysis is not None
            and translated_text.strip()
        ):
            try:
                # IMPORTANTE:
                #
                # Logistic Regression e soprattutto BERT sono
                # operazioni sincrone.
                #
                # Eseguendole direttamente qui bloccheremmo
                # l'event loop di Telethon.
                #
                # asyncio.to_thread consente al listener di
                # continuare a ricevere/elaborare eventi.
                ai_result = await asyncio.to_thread(
                    self.ai_analysis.analyze_message,
                    translated_text,
                    signal_hits=signal_hits,
                )

            except Exception:
                logger.exception(
                    "[MESSAGE PROCESSING] "
                    "Analisi AI fallita sul messaggio %s "
                    "nel gruppo %s.",
                    message.id,
                    group_id,
                )

                # Manteniamo un risultato strutturalmente valido.
                ai_result = self._empty_ai_result()

        meta = (
            ai_result.get("meta")
            or {}
        )

        # =========================================================
        # 6. PERSISTENZA AI
        # =========================================================

        ai_saved = False

        # La tabella AI ha una FK verso telegram_message.
        #
        # Inseriamo quindi l'enrichment solo quando il messaggio
        # RAW è stato persistito correttamente.
        if raw_saved:
            try:
                ai_values = self._build_ai_values(
                    message_id=message.id,
                    group_id=group_id,
                    ai_result=ai_result,
                    signal_hits=signal_hits,
                )

                ai_saved = (TelegramMessageAIAnalysisDatabaseManager.insert(entity_values=ai_values,))

            except Exception:
                logger.exception(
                    "[MESSAGE PROCESSING] "
                    "Salvataggio AI fallito per il messaggio %s "
                    "nel gruppo %s.",
                    message.id,
                    group_id,
                )

        # =========================================================
        # 7. NOTIFICHE
        # =========================================================

        try:
            await self._dispatch_notifications(
                message=message,
                group_id=group_id,
                raw_text=raw_text,
                translated_text=translated_text,
                signal_hits=signal_hits,
                ai_result=ai_result,
            )

        except Exception:
            logger.exception(
                "[MESSAGE PROCESSING] "
                "Invio notifiche fallito per il messaggio %s "
                "nel gruppo %s.",
                message.id,
                group_id,
            )

        # =========================================================
        # 8. RISULTATO PIPELINE
        # =========================================================

        return {
            "message_id": message.id,
            "group_id": group_id,

            "raw_saved": raw_saved,
            "ai_saved": ai_saved,

            "translation": translated_text,

            "signal_hits": signal_hits,
            "ai_result": ai_result,

            "risk_score": meta.get(
                "risk_score",
                0.0,
            ),

            "severity": meta.get(
                "severity",
                "low",
            ),

            "alert_recommended": bool(
                meta.get(
                    "alert_recommended",
                    False,
                )
            ),
        }

    async def _dispatch_notifications(
        self,
        *,
        message: Message,
        group_id: int,
        raw_text: str,
        translated_text: str,
        signal_hits: List[Dict[str, Any]],
        ai_result: Dict[str, Any],
    ) -> None:
        """
        Costruisce una sola rotta per ciascun notifier.

        Le notifiche configurate nelle regole Finder hanno priorità.

        Successivamente vengono aggiunte le destinazioni determinate
        dalla severity dell'analisi AI.
        """

        meta = (
            ai_result.get("meta")
            or {}
        )

        severity = str(
            meta.get("severity")
            or "low"
        ).lower()

        risk_score = float(
            meta.get("risk_score")
            or 0.0
        )

        alert_recommended = bool(
            meta.get(
                "alert_recommended",
                False,
            )
        )

        # notifier_name -> rule_id oppure None
        notification_routes: Dict[
            str,
            Optional[str],
        ] = {}

        # ---------------------------------------------------------
        # Finder routes
        # ---------------------------------------------------------

        for hit in signal_hits:
            rule_id = str(
                hit.get("id")
                or ""
            )

            for notifier_name in (
                hit.get("notifiers")
                or []
            ):
                notifier_name = str(
                    notifier_name
                ).strip()

                if notifier_name:
                    notification_routes[
                        notifier_name
                    ] = (
                        rule_id
                        or None
                    )

        # ---------------------------------------------------------
        # AI routes
        # ---------------------------------------------------------

        if alert_recommended:
            for notifier_name in (
                self._get_ai_notifiers(
                    severity
                )
            ):
                notification_routes.setdefault(
                    notifier_name,
                    None,
                )

        # ---------------------------------------------------------
        # Dispatch
        # ---------------------------------------------------------

        for (
            notifier_name,
            rule_id,
        ) in notification_routes.items():

            # Evita KeyError se il config contiene il nome
            # di un notifier non inizializzato.
            if (
                notifier_name
                not in self.notifier.notifiers
            ):
                logger.warning(
                    "[MESSAGE PROCESSING] "
                    "Notifier non configurato: %s",
                    notifier_name,
                )

                continue

            await self.notifier.run(
                message=message,
                notifiers=[
                    notifier_name
                ],
                translation=translated_text,
                raw_text=raw_text,
                group_id=group_id,
                id=message.id,
                rule_id=rule_id,
                severity=severity,
                risk_score=risk_score,
                rule_hits=signal_hits,
                ai_result=ai_result,
            )

    def _get_ai_notifiers(
        self,
        severity: str,
    ) -> List[str]:
        """
        Legge i notifier dal blocco [AI_ALERTING].

        Esempio:

            [AI_ALERTING]
            enabled = true

            medium_notifiers = NOTIFIER.DISCORD_STANDARD
            high_notifiers = NOTIFIER.DISCORD_ALERTS

            critical_notifiers =
                NOTIFIER.DISCORD_ALERTS,
                NOTIFIER.DISCORD_CRITICAL
        """

        if self.config is None:
            return []

        if not self.config.getboolean(
            "AI_ALERTING",
            "enabled",
            fallback=True,
        ):
            return []

        option_name = (
            f"{severity}_notifiers"
        )

        configured_value = self.config.get(
            "AI_ALERTING",
            option_name,
            fallback="",
        )

        notifiers = (
            self._parse_notifier_list(
                configured_value
            )
        )

        if notifiers:
            return notifiers

        # Fallback compatibile con il config attuale.
        defaults = {
            "medium": [
                "NOTIFIER.DISCORD_STANDARD",
            ],
            "high": [
                "NOTIFIER.DISCORD_ALERTS",
            ],
            "critical": [
                "NOTIFIER.DISCORD_ALERTS",
                "NOTIFIER.DISCORD_CRITICAL",
            ],
        }

        return defaults.get(
            severity,
            [],
        )

    @staticmethod
    def _parse_notifier_list(
        value: str,
    ) -> List[str]:
        """
        Converte una lista separata da virgole in nomi notifier.
        """

        return [
            item.strip()
            for item in value.split(",")
            if item.strip()
        ]

    @staticmethod
    def _extract_raw_text(
        message: Message,
    ) -> str:
        """
        Estrae il testo raw del messaggio Telegram.
        """

        raw_text = getattr(
            message,
            "raw_text",
            None,
        )

        if raw_text is None:
            raw_text = getattr(
                message,
                "message",
                None,
            )

        return str(
            raw_text
            or ""
        )

    @staticmethod
    def _build_raw_message_values(
        *,
        message: Message,
        group_id: int,
        media_id: Optional[int],
        raw_text: str,
        translated_text: str,
    ) -> Dict[str, Any]:
        """
        Costruisce l'entity dictionary per telegram_message.
        """

        return {
            "id": int(
                message.id
            ),

            "group_id": int(
                group_id
            ),

            "media_id": media_id,

            "date_time": (
                message.date
                or datetime.datetime.now(
                    datetime.timezone.utc
                )
            ),

            # Manteniamo il comportamento attuale:
            # message contiene il testo eventualmente tradotto.
            "message": translated_text,

            # raw conserva sempre il testo Telegram originale.
            "raw": raw_text,

            "from_id": (
                MessageProcessingService._extract_from_id(
                    message
                )
            ),

            "from_type": (
                MessageProcessingService._extract_from_type(
                    message
                )
            ),

            "to_id": (
                MessageProcessingService._extract_to_id(
                    message,
                    group_id,
                )
            ),

            "is_reply": bool(
                getattr(
                    message,
                    "reply_to_msg_id",
                    None,
                )
                or getattr(
                    message,
                    "reply_to",
                    None,
                )
            ),

            "reply_to_msg_id": getattr(
                message,
                "reply_to_msg_id",
                None,
            ),
        }

    def _build_ai_values(
        self,
        *,
        message_id: int,
        group_id: int,
        ai_result: Dict[str, Any],
        signal_hits: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Costruisce l'entity dictionary per
        telegram_message_ai_analysis.
        """

        activity = (
            ai_result.get("activity")
            or {}
        )

        attack_type = (
            ai_result.get("attack_type")
            or {}
        )

        target_nation = (
            ai_result.get("target_nation")
            or {}
        )

        meta = (
            ai_result.get("meta")
            or {}
        )

        return {
            "message_id": int(
                message_id
            ),

            "group_id": int(
                group_id
            ),

            # -----------------------------------------------------
            # JSON completo classificatori
            # -----------------------------------------------------

            "activity_json": json.dumps(
                activity,
                ensure_ascii=False,
                default=str,
            ),

            "attack_type_json": json.dumps(
                attack_type,
                ensure_ascii=False,
                default=str,
            ),

            "target_nation_json": json.dumps(
                target_nation,
                ensure_ascii=False,
                default=str,
            ),

            # -----------------------------------------------------
            # Top classifications
            # -----------------------------------------------------

            "top_activity": (
                activity.get(
                    "top_label"
                )
            ),

            "top_activity_score": (
                self._optional_float(
                    activity.get(
                        "top_score"
                    )
                )
            ),

            "top_attack_type": (
                attack_type.get(
                    "top_label"
                )
            ),

            "top_attack_type_score": (
                self._optional_float(
                    attack_type.get(
                        "top_score"
                    )
                )
            ),

            "top_target_nation": (
                target_nation.get(
                    "top_label"
                )
            ),

            "top_target_nation_score": (
                self._optional_float(
                    target_nation.get(
                        "top_score"
                    )
                )
            ),

            # -----------------------------------------------------
            # Metadata modello
            # -----------------------------------------------------

            "model_version": (
                self.model_version
            ),

            "created_at": (
                datetime.datetime.now(
                    datetime.timezone.utc
                )
            ),

            # -----------------------------------------------------
            # Risk / escalation
            # -----------------------------------------------------

            "risk_score": float(
                meta.get(
                    "risk_score"
                )
                or 0.0
            ),

            "severity": str(
                meta.get(
                    "severity"
                )
                or "low"
            ),

            "escalated_to_bert": bool(
                meta.get(
                    "escalated_to_bert",
                    False,
                )
            ),

            # -----------------------------------------------------
            # Finder signals
            # -----------------------------------------------------

            "rule_hits_json": json.dumps(
                signal_hits,
                ensure_ascii=False,
                default=str,
            ),

            "alert_recommended": bool(
                meta.get(
                    "alert_recommended",
                    False,
                )
            ),
        }

    @staticmethod
    def _optional_float(
        value: Any,
    ) -> Optional[float]:
        """
        Converte un valore in float mantenendo None.
        """

        if value is None:
            return None

        try:
            return float(value)

        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _extract_from_id(
        message: Message,
    ) -> Optional[int]:
        """
        Estrae l'ID del mittente.
        """

        sender_id = getattr(
            message,
            "sender_id",
            None,
        )

        if sender_id is not None:
            return int(
                sender_id
            )

        from_peer = getattr(
            message,
            "from_id",
            None,
        )

        return (
            MessageProcessingService._peer_to_id(
                from_peer
            )
        )

    @staticmethod
    def _extract_to_id(
        message: Message,
        group_id: int,
    ) -> Optional[int]:
        """
        Estrae il peer destinatario del messaggio.
        """

        peer = getattr(
            message,
            "peer_id",
            None,
        )

        peer_id = (
            MessageProcessingService._peer_to_id(
                peer
            )
        )

        if peer_id is not None:
            return peer_id

        return int(
            group_id
        )

    @staticmethod
    def _extract_from_type(
        message: Message,
    ) -> Optional[str]:
        """
        Restituisce il tipo di peer mittente.
        """

        from_peer = getattr(
            message,
            "from_id",
            None,
        )

        if from_peer is None:
            return None

        peer_type = type(
            from_peer
        ).__name__

        mapping = {
            "PeerUser": "user",
            "PeerChat": "chat",
            "PeerChannel": "channel",
        }

        return mapping.get(
            peer_type,
            peer_type[:10].lower(),
        )

    @staticmethod
    def _peer_to_id(
        peer: Any,
    ) -> Optional[int]:
        """
        Converte PeerUser/PeerChat/PeerChannel nel relativo ID.
        """

        if peer is None:
            return None

        for attribute in (
            "user_id",
            "chat_id",
            "channel_id",
        ):
            value = getattr(
                peer,
                attribute,
                None,
            )

            if value is not None:
                return int(
                    value
                )

        if isinstance(
            peer,
            int,
        ):
            return peer

        return None

    @staticmethod
    def _empty_task_result() -> Dict[str, Any]:
        """
        Risultato vuoto standardizzato per un task AI.
        """

        return {
            "labels": [],
            "scores": {},
            "top_label": None,
            "top_score": None,
            "source_model": "none",
        }

    @classmethod
    def _empty_ai_result(
        cls,
    ) -> Dict[str, Any]:
        """
        Risultato AI vuoto utilizzabile quando AI è disabilitata
        oppure un classificatore fallisce.
        """

        return {
            "activity": (
                cls._empty_task_result()
            ),

            "attack_type": (
                cls._empty_task_result()
            ),

            "target_nation": (
                cls._empty_task_result()
            ),

            "meta": {
                "risk_score": 0.0,
                "severity": "low",

                "escalated_to_bert": False,

                "escalation_reasons": [],

                "rule_hits_count": 0,
                "rule_hit_ids": [],

                "alert_recommended": False,
            },
        }
