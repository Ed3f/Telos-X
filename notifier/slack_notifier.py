from configparser import SectionProxy
from telethon.events import NewMessage

from TEx.notifier.notifier_base import BaseNotifier
from TEx.database.telegram_group_database import TelegramGroupDatabaseManager
from TEx.models.database.telegram_db_model import TelegramGroupOrmEntity
import requests
import re

class SlackNotifier(BaseNotifier): 

    def __init__(self) -> None:
        """Initialize Discord Notifier."""
        super().__init__()
        self.url: str = ''
    
    def configure(self, url: str, config: SectionProxy) -> None:
        """Configure the Notifier."""
        self.url = url
        self.configure_base(config=config)

    async def run(self, message: NewMessage.Event, **kwargs) -> None:
        group_id = kwargs['group_id']
        Webhook = self.url
        db_group= TelegramGroupDatabaseManager.get_by_id(group_id)
        username: str = db_group.group_username
        headers = {"Content-type": "application/json"}
        rule_id = kwargs['rule_id']
        if rule_id: 
            hot_stream = {"text":f"URL: https://t.me/{username}/{str(kwargs['id'])}\nOriginal message: {message}\nTraslation: {kwargs['raw_text']}"}
            #requests.post(Webhook, headers=headers, json=hot_stream)
            if kwargs['response']: 
                find= re.compile('https?:\/\/(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[i][t]')
                host_found = find.search(message)
                check_host= {"text": f"controllo host{host_found.group()}\nhost:{kwargs['response']}"}
                requests.post(Webhook, headers=headers, json= check_host)
        else: 
            standard_stream= {"text":f"URL: https://t.me/{username}/{str(kwargs['id'])}\nTraslation: {kwargs['translation']}"}
            #requests.post(Webhook, headers=headers, json=standard_stream)
