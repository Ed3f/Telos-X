"""Notifier Modules."""
from configparser import ConfigParser
from typing import Dict, List

from telethon.events import NewMessage

from telos_x.notifier.discord_notifier import DiscordNotifier
from telos_x.notifier.slack_notifier import SlackNotifier
from telos_x.notifier.notifier_base import BaseNotifier
from typing import Dict, List, Optional


class NotifierEngine:
    """Primary Notification Engine."""

    def __init__(self) -> None:
        """Initialize Finder Engine."""
        self.notifiers: Dict = {}

    def __load_notifiers(self, config: ConfigParser) -> None:
        """Load all Registered Notifiers."""
        registered_notifiers: List[str] = [item for item in config.sections() if 'NOTIFIER.' in item]

        for register in registered_notifiers:
            if 'DISCORD' in register:

                notifier: DiscordNotifier = DiscordNotifier()
                notifier.configure(url=config[register]['webhook'], config=config[register])

                self.notifiers.update({
                    register: {'instance': notifier}
                    })
            if 'SLACK' in register: 
                notifier: SlackNotifier = SlackNotifier()
                notifier.configure(url=config[register]['webhook'], config=config[register])

                self.notifiers.update({
                    register: {'instance': notifier}
                    })

    def configure(self, config: ConfigParser) -> None:
        """Configure Finder."""
        self.__load_notifiers(config)

   
    async def run(self, message: NewMessage.Event, notifiers: Optional[List[str]] = None, **kwargs) -> None:
        if notifiers is None:
            notifiers = list(self.notifiers.keys())

        for dispatcher_name in notifiers:
            target_notifier: BaseNotifier = self.notifiers[dispatcher_name]['instance']
            await target_notifier.run(message=message, **kwargs)