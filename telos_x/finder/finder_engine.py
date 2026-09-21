from __future__ import annotations

import asyncio
import logging

from configparser import ConfigParser
from typing import Dict, List

from telethon.tl.types import Message

from telos_x.finder.regex_finder import RegexFinder
from telos_x.notifier.notifier_engine import NotifierEngine
from telos_x.utils.check_host import check_host


logger = logging.getLogger(__name__)


class FinderEngine:
    """Primary Finder Engine."""

    def __init__(self) -> None:
        self.is_finder_enabled: bool = False
        self.rules: List[Dict] = []
        self.notification_engine = NotifierEngine()

    def configure(
        self,
        config: ConfigParser,
    ) -> None:
        """
        Configura Finder e relative regole.

        Ogni chiamata a configure() ricostruisce completamente
        l'elenco delle regole, evitando configurazioni residue.
        """

        self.notification_engine.configure(
            config=config
        )

        self.is_finder_enabled = config.getboolean(
            "FINDER",
            "enabled",
            fallback=False,
        )

        # Reset sempre, anche se Finder viene disabilitato dopo
        # una precedente configurazione.
        self.rules = []

        if not self.is_finder_enabled:
            return

        registered_rules: List[str] = [
            section
            for section in config.sections()
            if section.startswith(
                "FINDER.RULE."
            )
        ]

        for rule_id in registered_rules:
            regex = config.get(
                rule_id,
                "regex",
                fallback="",
            ).strip()

            # Una regola senza regex non è utilizzabile.
            if not regex:
                continue

            notifiers = [
                item.strip()
                for item in config.get(
                    rule_id,
                    "notifier",
                    fallback="",
                ).split(",")
                if item.strip()
            ]

            severity_hint = config.get(
                rule_id,
                "severity_hint",
                fallback="medium",
            ).strip().lower()

            # Evitiamo severity arbitrarie nel RiskScorer.
            if severity_hint not in {
                "low",
                "medium",
                "high",
                "critical",
            }:
                severity_hint = "medium"

            try:
                finder = RegexFinder(regex=regex)
            except Exception as exc:
                logger.warning('Ignoring invalid Finder rule %s: %s', rule_id, exc)
                continue

            self.rules.append(
                {
                    "id": rule_id,
                    "instance": finder,
                    "notifiers": notifiers,
                    "severity_hint": severity_hint,
                }
            )

    async def find_signals(
        self,
        message: Message,
        **kwargs,
    ) -> List[Dict]:
        """
        Cerca segnali CTI nel messaggio.

        La ricerca viene eseguita sia sul testo originale sia,
        quando differente, sulla traduzione.

        Il testo originale viene mantenuto per operazioni sugli IOC,
        come check_host(), perché URL, domini e identificatori non
        dovrebbero dipendere dalla traduzione.
        """

        if not self.is_finder_enabled:
            return []

        # =========================================================
        # 1. TESTO ORIGINALE
        # =========================================================

        original_text = (
            kwargs.get("raw_text")
            or getattr(
                message,
                "raw_text",
                None,
            )
            or getattr(
                message,
                "message",
                None,
            )
            or ""
        )

        # =========================================================
        # 2. TESTO TRADOTTO
        # =========================================================

        translated_text = (
            kwargs.get("translation")
            or ""
        )

        # =========================================================
        # 3. TESTO UTILIZZATO DAL FINDER
        # =========================================================

        search_text = original_text

        if (
            translated_text
            and translated_text != original_text
        ):
            search_text = (
                original_text
                + "\n"
                + translated_text
            )

        # Nessun contenuto da analizzare.
        if not search_text.strip():
            return []

        hits: List[Dict] = []

        # =========================================================
        # 4. APPLICAZIONE DELLE REGOLE
        # =========================================================

        for rule in self.rules:
            try:
                is_found: bool = (
                    await rule[
                        "instance"
                    ].find(
                        raw_text=search_text
                    )
                )

            except Exception:
                # Una singola regex non deve interrompere tutte
                # le altre regole Finder.
                logger.exception('Finder rule %s failed; continuing', rule['id'])
                continue

            if not is_found:
                continue

            response = None

            # =====================================================
            # 5. URL ENRICHMENT
            # =====================================================

            if (
                rule["id"]
                == "FINDER.RULE.MessagesWithURL"
            ):
                try:
                    # check_host è sincrono e contiene anche sleep;
                    # viene quindi eseguito fuori dall'event loop.
                    #
                    # Usiamo il testo ORIGINALE per preservare
                    # esattamente URL/domain/IOC.
                    response = await asyncio.to_thread(
                        check_host,
                        original_text,
                    )

                except Exception:
                    response = None

            # =====================================================
            # 6. HIT STRUTTURATO
            # =====================================================

            hits.append(
                {
                    "id": rule["id"],
                    "notifiers": rule[
                        "notifiers"
                    ],
                    "response": response,
                    "severity_hint": rule[
                        "severity_hint"
                    ],
                }
            )

        return hits

    async def run(
        self,
        message: Message,
        **kwargs,
    ) -> None:
        """
        Mantiene compatibilità con il vecchio Finder.

        La nuova pipeline utilizza principalmente find_signals(),
        che restituisce hit strutturati. Questo metodo continua
        invece a inviare direttamente le notifiche per i moduli
        legacy che ancora lo utilizzano.
        """

        hits = await self.find_signals(
            message,
            **kwargs,
        )

        for hit in hits:
            await self.notification_engine.run(
                message=message,
                notifiers=hit[
                    "notifiers"
                ],
                rule_id=hit[
                    "id"
                ],
                response=hit[
                    "response"
                ],
                severity_hint=hit[
                    "severity_hint"
                ],
                **kwargs,
            )
