"""Telegram Group Listener."""
import logging
from configparser import ConfigParser
from typing import Dict, List, cast


from utils import active_groups, Os_stat,Translation_function
import pytz
from functools import partial
from telethon import TelegramClient, events
from telethon.events import NewMessage, MessageEdited, MessageDeleted, ChatAction
from telethon.tl.types import (Channel, Message, PeerUser, User)
from telethon.tl.functions.channels import JoinChannelRequest


import signal
from TEx.core.base_module import BaseModule
from TEx.core.mapper.telethon_channel_mapper import TelethonChannelEntityMapper
from TEx.core.mapper.telethon_user_mapper import TelethonUserEntiyMapper
from TEx.core.media_handler import UniversalTelegramMediaHandler
from TEx.database.telegram_group_database import TelegramGroupDatabaseManager, TelegramMessageDatabaseManager, \
    TelegramUserDatabaseManager
from TEx.finder.finder_engine import FinderEngine
from TEx.notifier.notifier_engine import NotifierEngine

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
        self.media_handler: UniversalTelegramMediaHandler = UniversalTelegramMediaHandler()
        self.target_phone_number: str = ''
        self.finder: FinderEngine = FinderEngine()
        self.notifier: NotifierEngine = NotifierEngine()
    
    async def __new_message_handler(self, client:TelegramClient, event: NewMessage.Event) -> None:
        """Handle the Message."""
        # Get Message
        message: Message = event.message

        # Apply Filter (If group filtering are enabled)
        if len(self.group_ids) > 0 and event.chat.id not in self.group_ids:
            logger.debug(f'\t\tMessage Filtered (GroupID={event.chat.id}) ...')
            return

  
        if event and not event.chat:
            return  # TO_DO: Need to Be Handled in Future Version


        # Ensure Group Exists on DB
        await self.__ensure_group_exists(event=event)

        # Create Dict with All Value
        values: Dict = {
            'id': message.id,
            'group_id': event.chat.id,
            'date_time': message.date.astimezone(tz=pytz.utc),
            'message': message.message,
            'raw': message.raw_text,
            'to_id': message.to_id.channel_id if message.to_id is not None else None,
            'media_id': await self.media_handler.handle_medias(message, event.chat.id, self.data_path) if self.download_media else None,
            'is_reply': message.is_reply,
            'reply_to_msg_id': message.reply_to.reply_to_msg_id if message.is_reply else None
            }
        if message.message:
            #Funzione di traduzione
            translation = await Translation_function.translate(values['message'], client)
            
        
        # Process Sender ID
        if message.from_id is not None:
            if isinstance(message.from_id, PeerUser):

                values['from_id'] = message.from_id.user_id
                values['from_type'] = 'User'

                # Ensure User Exists
                await self.__ensure_user_exists(event=event)

            else:
                values['from_id'] = None
                values['from_type'] = None

        # Execute Finder
        await self.finder.run(message=message, translation=translation, group_id = values['group_id'], id= values['id'])
        
        #Execute Notifier
        rule_id= None 
        await self.notifier.run(message=message, translation=translation, group_id= values['group_id'], id= values['id'],rule_id= rule_id)

        # Add to DB
        TelegramMessageDatabaseManager.insert(values)      

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


    async def __ensure_user_exists(self, event: NewMessage.Event) -> None:
        """
        Ensure the User Exists on DB.

        :param event:
        :return:
        """
        # Check if User Already in DB or is New One -- REFACTORY
        if not TelegramUserDatabaseManager.get_by_id(pk=event.from_id.user_id):
            logger.warning(
                f'\t\tUser "{event.from_id.user_id}" was not found on DB. Performing automatic synchronization.')

            # Retrieve User
            result: User = await event.get_sender()

            # Perform Synchronization
            if result:
                user_dict_data: Dict = TelethonUserEntiyMapper.to_database_dict(result)
                TelegramUserDatabaseManager.insert_or_update(user_dict_data)

    async def __ensure_group_exists(self, event: NewMessage.Event) -> None:
        """
        Ensure the Group/Channel Exists on DB.

        :param event:
        :return:
        """
        # Check if Group Already in DB or is New One
        if not TelegramGroupDatabaseManager.get_by_id(pk=event.chat.id):
            logger.warning(
                f'\t\tGroup "{event.chat.id}" not found on DB. Performing automatic synchronization. Consider execute "load_groups" command to perform a full group synchronization (Members and Group Cover Photo).')

            # Retrieve Group Definitions
            result: Channel = await event.get_chat()

            # Perform Synchronization
            if result:
                group_dict_data: Dict = TelethonChannelEntityMapper.to_database_dict(
                    entity=result,
                    target_phone_numer=self.target_phone_number
                    )

                TelegramGroupDatabaseManager.insert_or_update(group_dict_data)
    


    async def run(self, config: ConfigParser, args: Dict, data: Dict) -> None:
        """Execute Module."""
        if not await self.can_activate(config, args, data):
            logger.debug('\t\tModule is Not Enabled...')
            return

        # Update Module Global Info
        self.download_media = not args['ignore_media']
        self.data_path = config['CONFIGURATION']['data_path']
        self.target_phone_number = config['CONFIGURATION']['phone_number']

        client = data['telegram_client']

        # Set Finder
        self.finder.configure(config=config)

        # Set Notifier
        self.notifier.configure(config=config)

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
            
