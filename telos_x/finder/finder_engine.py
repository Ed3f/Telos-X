from __future__ import annotations

from configparser import ConfigParser
from typing import Dict, List

from telethon.events import NewMessage

from telos_x.finder.regex_finder import RegexFinder
from telos_x.notifier.notifier_engine import NotifierEngine
from telos_x.utils.check_host import check_host


class FinderEngine:
    """Primary Finder Engine."""

    def __init__(self) -> None:
        self.is_finder_enabled: bool = False
        self.rules: List[Dict] = []
        self.notification_engine = NotifierEngine()

    def configure(self, config: ConfigParser) -> None:
        self.notification_engine.configure(config=config)
        self.is_finder_enabled = config.getboolean("FINDER", "enabled", fallback=False)

        if not self.is_finder_enabled:
            return

        registered_rules: List[str] = [item for item in config.sections() if item.startswith("FINDER.RULE.")]
        self.rules = []

        for rule_id in registered_rules:
            self.rules.append({
                "id": rule_id,
                "instance": RegexFinder(regex=config[rule_id]["regex"]),
                "notifiers": [
                    item.strip()
                    for item in config[rule_id].get("notifier", "").split(",")
                    if item.strip()
                ],
            })

    async def find_signals(self, message: NewMessage.Event, **kwargs) -> List[Dict]:
        if not self.is_finder_enabled:
            return []

        raw_text = kwargs.get("translation") or message.raw_text or ""
        hits: List[Dict] = []

        for rule in self.rules:
            is_found: bool = await rule["instance"].find(raw_text=raw_text)
            if not is_found:
                continue

            response = None
            if rule["id"] == "FINDER.RULE.MessagesWithURL":
                response = check_host(message.message)

            hits.append({
                "id": rule["id"],
                "notifiers": rule["notifiers"],
                "response": response,
                "severity_hint": "high" if response else "medium",
            })

        return hits

    async def run(self, message: NewMessage.Event, **kwargs) -> None:
        hits = await self.find_signals(message, **kwargs)

        for hit in hits:
            await self.notification_engine.run(
                message=message,
                notifiers=hit["notifiers"],
                rule_id=hit["id"],
                response=hit["response"],
                **kwargs,
            )