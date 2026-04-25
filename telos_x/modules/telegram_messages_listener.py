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

logging.basicConfig(filename='example.log', encoding='utf-8', level=logging.DEBUG)
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

        # Apply Filter (If group filtering are enabled)
        if len(self.group_ids) > 0 and event.chat.id not in self.group_ids:
            logger.debug(f'\t\tMessage Filtered (GroupID={event.chat.id}) ...')
            return

        # Defensive check
        if event and not event.chat:
            return

        # Delegate the whole processing pipeline
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

    async def __message_edited_handler(self, event:MessageEdited.Event) -> None:
        print('Message', event.id, 'changed at', event.date)

    async def __message_deleted_handler(self, event:MessageDeleted.Event) -> None:
        for msg_id in event.deleted_ids:
            print('Message', msg_id,'was deleted in', event.chat_id)

    async def __chat_action_handler(self, event:ChatAction.Event) -> None:
        if event.user_joined:
            user_info=  await event.get_user()
            #Notifier.alertUserToJoinGroup(user_info)
        if event.user_added:       
            user_info_to_add= await event.get_added_by()
            #Notifier.alertUserToJoinGroup(user_info_to_add)                
        if event.user_left:
            user_info_to_left= await event.get_user()
            #Notifier.alertUserToJoinGroup(user_info_to_left)
        if event.get_pinned_messages:
            pinned_message=await event.get_pinned_messages()


    



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
            
