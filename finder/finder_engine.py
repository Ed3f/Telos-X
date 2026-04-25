"""Finder Engine."""
from configparser import ConfigParser
from typing import Dict, List

from telethon.events import NewMessage

from TELOSX.finder.regex_finder import RegexFinder
from TELOSX.notifier.notifier_engine import NotifierEngine
from TELOSX.utils.check_host import check_host


class FinderEngine:
    """Primary Finder Engine."""

    def __init__(self) -> None:
        """Initialize Finder Engine."""
        self.is_finder_enabled: bool = False
        self.rules: List[Dict] = []
        self.notification_engine: NotifierEngine = NotifierEngine()

    def __is_finder_enabled(self, config: ConfigParser) -> bool:
        """Check if Finder Module is Enabled."""
        return (
            config.has_option('FINDER', 'enabled') and config['FINDER']['enabled'] == 'true'
            )

    def __load_rules(self, config: ConfigParser) -> None:
        """Load Finder Rules."""
        rules_sections: List[str] = [item for item in config.sections() if 'FINDER.RULE.' in item]

        for sec in rules_sections:
            if config[sec]['type'] == 'regex':
                self.rules.append({
                    'id': sec,
                    'instance': RegexFinder(config=config[sec]),
                    'notifier': config[sec]['notifier']
                    })

    def configure(self, config: ConfigParser) -> None:
        """Configure Finder."""
        self.is_finder_enabled = self.__is_finder_enabled(config=config)
        print(self.is_finder_enabled)
        self.__load_rules(config=config)
        self.notification_engine.configure(config=config)

    async def run(self, message: NewMessage.Event, **kwargs) -> None:
        """Execute the Finder with Raw Text."""
        if not self.is_finder_enabled:
            return
        for rule in self.rules:
            raw_text= kwargs['translation']
            is_found: bool = await rule['instance'].find(raw_text= raw_text)
            rule_id= rule['id']
            response = None 
            
            #controlla che l'host trovato sia .it  o governativo e invia il controllo 
            if rule_id == "FINDER.RULE.MessagesWithURL":
                response = check_host(message.message)

            if is_found:

                # Run the Notification Engine
                await self.notification_engine.run(
                    message=message,
                    notifiers=rule['notifier'].split(','),  
                    group_id= kwargs['group_id'],
                    id= kwargs['id'],
                    translation= kwargs['translation'],
                    raw_text= raw_text, 
                    rule_id=rule_id, 
                    response = response  
                )
            