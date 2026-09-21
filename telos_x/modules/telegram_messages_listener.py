"""Telegram Group Listener."""
import logging
from configparser import ConfigParser
from typing import Dict, List, cast



from functools import partial
from telethon import TelegramClient, events
from telethon.events import NewMessage, MessageEdited, MessageDeleted, ChatAction
from telethon.tl.types import Message


from telos_x.core.base_module import BaseModule
from telos_x.services.message_processing import MessageProcessingService

logger = logging.getLogger('TelegramExplorer')

class TelegramGroupMessageListener(BaseModule):
    """Download all Messages from Telegram Groups."""

    async def can_activate(self, config: ConfigParser, args: Dict, data: Dict) -> bool:
        """
        Abstract Method for Module Activation Function.
        :return:
        """

        return cast(bool, args['listen'])
    
    def __init__(self) -> None:
        """Initialize Listener Module."""
        self.download_media: bool = False
        self.data_path: str = ''
        self.group_ids: List[int] = []
        self.target_phone_number: str = ''
        self.processor = MessageProcessingService()
        
    async def __new_message_handler(self, client:TelegramClient, event: NewMessage.Event) -> None:
        """Handle the Message."""
        message: Message = event.message

        if event is None or event.chat is None:
            return
        if (self.group_ids and event.chat.id not in self.group_ids):
            logger.debug(
                "Message Filtered (GroupID=%s)",
                event.chat.id,
            )
            return

        try:
            await self.processor.process_message(
                message=message,
                group_id=event.chat.id,
                client=client,
                data_path=self.data_path,
                download_media=self.download_media,
                target_phone_number=self.target_phone_number,
                pipeline="realtime",
                chat=event.chat,
                event=event,
            )
        except Exception:
            logger.exception(
                'Unexpected realtime processing failure for message %s; '
                'the listener remains active',
                getattr(message, 'id', 'unknown'),
            )

    async def __message_edited_handler(self, event:MessageEdited.Event) -> None:
        logger.info('Message %s changed at %s', event.id, event.date)

    async def __message_deleted_handler(self, event:MessageDeleted.Event) -> None:
        for msg_id in event.deleted_ids:
            logger.info('Message %s was deleted in %s', msg_id, event.chat_id)

    async def __chat_action_handler(self, event:ChatAction.Event) -> None:
        if event.user_joined:
            user_info = await event.get_user()
            logger.info('User joined: %s', getattr(user_info, 'id', 'unknown'))
        if event.user_added:
            user_info_to_add = await event.get_added_by()
            logger.info('User added by: %s', getattr(user_info_to_add, 'id', 'unknown'))
        if event.user_left:
            user_info_to_left = await event.get_user()
            logger.info('User left: %s', getattr(user_info_to_left, 'id', 'unknown'))
        if getattr(event, 'new_pin', False):
            await event.get_pinned_messages()


    



    async def run(self, config: ConfigParser, args: Dict, data: Dict) -> None:
        """Execute Module."""
        if not await self.can_activate(config, args, data):
            logger.debug('\t\tModule is Not Enabled...')
            return

        # Update Module Global Info
        self.download_media = not args['ignore_media']
        self.data_path = config['CONFIGURATION']['data_path']
        self.target_phone_number = config['CONFIGURATION']['phone_number']
        self.processor.configure(config)

        client = data['telegram_client']

        # Update Module Group Filtering Info
        if args['group_id'] and args['group_id'] != '*':
            self.group_ids = [int(group_id) for group_id in args['group_id'].split(',')]
            logger.info(f'\t\tApplied Groups Filtering... {len(self.group_ids)} selected')

        # Register Handlers
        client.add_event_handler(partial(self.__new_message_handler, client), events.NewMessage)
        client.add_event_handler(self.__message_edited_handler, events.MessageEdited)
        client.add_event_handler(self.__message_deleted_handler, events.MessageDeleted)
        client.add_event_handler(self.__chat_action_handler, events.ChatAction)
        
        # Catch Up Past Messages
        logger.info('\t\tListening Past Messages...')
        await client.catch_up()

        # Read all Messages from Now #parti da implementare nel listener  #traduzione messaggi #messaggio di informazione di spazio memoria  
        logger.info('\t\tListening New Messages...')

        #signal.signal(signal.SIGINT)

        await client.run_until_disconnected()  # Code Stops Here until telegram disconnects
        logger.info('\t\tTelegram Client Disconnected...')
            
