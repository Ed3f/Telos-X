from configparser import SectionProxy
import re
import requests
from telethon.events import NewMessage

from TELOSX.notifier.notifier_base import BaseNotifier
from TELOSX.database.telegram_group_database import TelegramGroupDatabaseManager


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
        is_duplicated, _ = self.check_is_duplicated(message=message.raw_text)
        if is_duplicated:
            return

        rule_id = kwargs.get('rule_id')
        if self.only_rule_matches and not rule_id:
            return

        group_id = kwargs['group_id']
        db_group = TelegramGroupDatabaseManager.get_by_id(group_id)
        username = db_group.group_username if db_group and db_group.group_username else "unknown_group"

        headers = {"Content-type": "application/json"}
        translation = kwargs.get("translation", message.raw_text or "")
        raw_text = kwargs.get("raw_text", message.raw_text or "")

        payload = {
            "text": (
                f"URL: https://t.me/{username}/{kwargs['id']}\n"
                f"Original message: {raw_text}\n"
                f"Translation: {translation}"
            )
        }

        if rule_id:
            payload["text"] += f"\nRule ID: {rule_id}"

        requests.post(self.url, headers=headers, json=payload)