import asyncio
from configparser import SectionProxy

import requests
from telethon.events import NewMessage

from telos_x.notifier.notifier_base import BaseNotifier
from telos_x.database.telegram_group_database import TelegramGroupDatabaseManager


class SlackNotifier(BaseNotifier):
    def __init__(self) -> None:
        super().__init__()
        self.url: str = ''
        self.only_rule_matches: bool = False

    def configure(self, url: str, config: SectionProxy) -> None:
        self.url = url
        self.configure_base(config=config)
        self.only_rule_matches = (
            'only_rule_matches' in config
            and config['only_rule_matches'].lower() == 'true'
        )

    async def run(self, message: NewMessage.Event, **kwargs) -> None:
        raw_message_text = getattr(message, 'raw_text', None) or ''
        is_duplicated, _ = self.check_is_duplicated(message=raw_message_text)
        if is_duplicated:
            return

        rule_id = kwargs.get('rule_id')
        if self.only_rule_matches and not rule_id:
            return

        group_id = kwargs.get('group_id')
        db_group = TelegramGroupDatabaseManager.get_by_id(group_id)
        username = db_group.group_username if db_group and db_group.group_username else "unknown_group"

        headers = {"Content-type": "application/json"}
        translation = kwargs.get("translation", raw_message_text)
        raw_text = kwargs.get("raw_text", raw_message_text)

        payload = {
            "text": (
                f"URL: https://t.me/{username}/{kwargs.get('id', 'unknown')}\n"
                f"Original message: {raw_text}\n"
                f"Translation: {translation}"
            )
        }

        if rule_id:
            payload["text"] += f"\nRule ID: {rule_id}"

        response = await asyncio.to_thread(
            requests.post,
            self.url,
            headers=headers,
            json=payload,
            timeout=10,
        )

        response.raise_for_status()

    async def send_text(self, text: str) -> None:
        """Send a generic status message through the configured webhook."""
        is_duplicated, _ = self.check_is_duplicated(message=text)
        if is_duplicated:
            return
        response = await asyncio.to_thread(
            requests.post,
            self.url,
            headers={"Content-type": "application/json"},
            json={"text": text},
            timeout=10,
        )
        response.raise_for_status()
