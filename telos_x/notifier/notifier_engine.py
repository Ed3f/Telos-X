"""Notifier Engine."""

import logging

from configparser import ConfigParser
from typing import Dict, List, Optional

from telethon.events import NewMessage

from telos_x.notifier.discord_notifier import (
    DiscordNotifier,
)

from telos_x.notifier.notifier_base import (
    BaseNotifier,
)

from telos_x.notifier.slack_notifier import (
    SlackNotifier,
)


logger = logging.getLogger(
    "TelegramExplorer"
)


class NotifierEngine:
    """Primary Notification Engine."""

    def __init__(
        self,
    ) -> None:

        self.notifiers: Dict = {}

    def __load_notifiers(
        self,
        config: ConfigParser,
    ) -> None:

        registered_notifiers: List[str] = [
            section
            for section
            in config.sections()
            if section.startswith(
                "NOTIFIER."
            )
        ]

        for register in registered_notifiers:

            webhook = config.get(
                register,
                "webhook",
                fallback="",
            ).strip()

            if not webhook:
                logger.warning(
                    "[NOTIFIER] Missing webhook: %s",
                    register,
                )
                continue

            try:
                self._load_notifier(register, webhook, config)
            except Exception:
                logger.exception(
                    '[NOTIFIER] Invalid notifier configuration %s; continuing',
                    register,
                )

    def _load_notifier(
        self,
        register: str,
        webhook: str,
        config: ConfigParser,
    ) -> None:
        """Initialize one notifier section without affecting its siblings."""
        if "DISCORD" in register:

            notifier = DiscordNotifier()

            notifier.configure(url=webhook, config=config[register])

            self.notifiers[register] = {"instance": notifier}

        elif "SLACK" in register:

            notifier = SlackNotifier()

            notifier.configure(url=webhook, config=config[register])

            self.notifiers[register] = {"instance": notifier}
        else:
            logger.warning('[NOTIFIER] Unsupported notifier section: %s', register)

    def configure(
        self,
        config: ConfigParser,
    ) -> None:

        # Evita notifier residui
        # dopo una seconda configure().
        self.notifiers = {}

        self.__load_notifiers(
            config
        )

    async def run(
        self,
        message: NewMessage.Event,
        notifiers:
            Optional[List[str]]
            = None,
        **kwargs,
    ) -> None:

        if notifiers is None:
            notifiers = list(
                self.notifiers.keys()
            )

        for dispatcher_name in notifiers:

            entry = self.notifiers.get(
                dispatcher_name
            )

            if entry is None:
                logger.warning(
                    "[NOTIFIER] Unknown notifier: %s",
                    dispatcher_name,
                )
                continue

            target_notifier: BaseNotifier = (
                entry["instance"]
            )

            try:
                await target_notifier.run(
                    message=message,
                    **kwargs,
                )
            except Exception:
                logger.exception(
                    '[NOTIFIER] Delivery failed for %s; continuing',
                    dispatcher_name,
                )

    async def send_text(
        self,
        text: str,
        notifiers: Optional[List[str]] = None,
    ) -> None:
        """Send operational text through configured notifier instances."""
        if notifiers is None:
            notifiers = list(self.notifiers.keys())

        for dispatcher_name in notifiers:
            entry = self.notifiers.get(dispatcher_name)
            if entry is None:
                logger.warning("[NOTIFIER] Unknown notifier: %s", dispatcher_name)
                continue
            target_notifier: BaseNotifier = entry["instance"]
            try:
                await target_notifier.send_text(text)
            except Exception:
                logger.exception(
                    '[NOTIFIER] Operational delivery failed for %s; continuing',
                    dispatcher_name,
                )
