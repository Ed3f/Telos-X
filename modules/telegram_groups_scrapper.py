"""Telegram Group Scrapper."""

import pandas
import re
import base64
import json
import logging
import os
import pathlib
from configparser import ConfigParser
from typing import Dict, List, Optional, Tuple, cast
import random
from time import sleep
from datetime import datetime


from telethon import functions, types
import telethon.tl.types
from telethon import TelegramClient
from telethon.errors import ChatAdminRequiredError
from telethon.tl.functions.messages import GetDialogsRequest
from telethon.tl.types import ChatPhoto, InputPeerEmpty
from telethon.tl.types.messages import Dialogs
from telethon.tl.functions.channels import JoinChannelRequest
from TELOSX.models.database.telegram_db_model import TelegramGroupOrmEntity
from telethon.errors import ChannelPrivateError, InviteRequestSentError

from TELOSX.core.base_module import BaseModule
from TELOSX.core.mapper.telethon_channel_mapper import TelethonChannelEntityMapper
from TELOSX.core.temp_file import TempFileHandler
from TELOSX.database.telegram_group_database import TelegramGroupDatabaseManager, TelegramUserDatabaseManager, TelegramProfilePicDatabaseManager
from TELOSX.core.mapper.telethon_user_mapper import TelethonUserEntiyMapper

logger = logging.getLogger('TelegramExplorer')


class TelegramGroupScrapper(BaseModule):
    """List all Groups on Telegram Account."""

    async def can_activate(self, config: ConfigParser, args: Dict, data: Dict) -> bool:
        """
        Abstract Method for Module Activation Function.

        :return:
        """
        return cast(bool, args['load_groups'])

    async def run(self, config: ConfigParser, args: Dict, data: Dict) -> None:
        """Execute Module."""
        if not await self.can_activate(config, args, data):
            logger.debug('\t\tModule is Not Enabled...')
            return

        # Check Data Dict
        if 'groups' not in data:
            data['groups'] = {}
            print(data['groups'])
        if 'members' not in data:
            data['members'] = {}

        # Get Client
        client: TelegramClient = data['telegram_client']
        #Get all Groups on Db 
        db_groups: List[TelegramGroupOrmEntity] = TelegramGroupDatabaseManager.get_all_by_phone_number(
            config['CONFIGURATION']['phone_number'])
        db_chat_usrs= [chat.group_username for chat in db_groups]
        #Get all Groups from CSV file
        link_group = pandas.read_csv("groups.csv")
        find_group= re.compile("(?:t|telegram)\.(?:me|dog)\/(joinchat\/|\+)?([\w-]+)")

        for groups in link_group['telegram_group']:
            found = find_group.search(groups)

            if found:
                usr=found#così ottendo l'username
                print(usr.group(2))
                if (usr.group(2) not in db_chat_usrs):
                    minutes = random.randint(1, 3)
                    print(minutes)
                    sleep(minutes)
                    #channel= await client(JoinChannelRequest(usr.group(2)))
                    #print(channel)
                    logger.info("Puppet account are join in the group\n")
        
        #Write Groups on file from DB 
        # Get all Chats
        chats: List = await self.load_groups(
            client=client
            )
        
        db_chats_ids = [chat.id for chat in db_groups]
        chat_ids = [chat.id for chat in chats]
        
        new_chats = []
        deleted_chats = []

        for chat in chats:
            if (chat.username):
                #call to obtain discussion group of channel
                full= await client(functions.channels.GetFullChannelRequest(chat.id))
                full_channel= full.full_chat
                
                #Join on discussion group
                if full_channel.linked_chat_id:
                    linked_group = next(c for c in full.chats if c.id == full_channel.linked_chat_id)
                    print(linked_group.username)

            if chat.id not in db_chats_ids:
                new_chats.append(chat.title)
        
        for group in db_groups:
            if group.id not in chat_ids:    
                deleted_chats.append(group.title)

                

        with open("not_active_group.txt", "w") as file:
            
            file.write("gruppi che non sono più monitorati:\n")
            file.write('\n'.join(deleted_chats))
        
            file.write("Gruppi Monitorati dalla sonda\n")
            file.write('\n'.join([chat.title for chat in chats]))
            
        for chat in chats:
             
            logger.info(f'\t\tProcessing "{chat.title} ({chat.id})" Members and Group Profile Picture')
            
            values: Dict = TelethonChannelEntityMapper.to_database_dict(
                entity=chat,
                target_phone_numer=config['CONFIGURATION']['phone_number']
                )

            # Get Photo - TODO: Refactory - Separate in Method
            if chat.photo is not None and isinstance(chat.photo, ChatPhoto):
                values['photo_id'] = chat.photo.photo_id
                photo_name, photo_base64 = await self.get_profile_pic_b64(
                    client=client,
                    channel=chat,
                    data_path=config['CONFIGURATION']['data_path'],
                    force_reload=args['refresh_profile_photos']
                    )

                values['photo_base64'] = photo_base64
                values['photo_name'] = photo_name
            else:
                values['photo_id'] = None
                values['photo_base64'] = None
                values['photo_name'] = None

            # Get Members - TODO: Refactory - Separate in Method
            try:
                members = await self.get_members(
                    client=client,
                    channel=chat,
                    data_path = config['CONFIGURATION']['data_path']
                    )
                # Sync with DB
                TelegramUserDatabaseManager.insert_or_update_batch(members)

            except telethon.errors.rpcerrorlist.ChannelPrivateError:
                logger.info('\t\t\t...Unable to Download Chat Participants due Private Chat Restrictions...')
            except ValueError as _ex:
                if 'PeerChannel' in _ex.args[0]:
                    logger.info('\t\t\t...Unable to Download Chat Participants due PerChannel Restrictions...')
                    continue
                raise _ex
            except TypeError as _ex:
                if "'ChannelParticipants' object is not subscriptable" in _ex.args[0]:
                    logger.info('\t\t\t...Unable to Download Chat Participants due ChannelParticipants Restrictions...')
                    continue
                raise _ex

            # Add Group to DB
            TelegramGroupDatabaseManager.insert_or_update(values)

    async def load_groups(self, client: TelegramClient) -> List[telethon.tl.types.Channel]:
        """Load all Groups from Telegram."""
        logger.info("\t\tEnumerating Groups")

        # DownLoad Groups
        result: Dialogs = await client(GetDialogsRequest(
            offset_date=None,
            offset_id=0,
            offset_peer=InputPeerEmpty(),
            limit=20000,
            hash=0
            ))

        return [chat for chat in result.chats if isinstance(chat, telethon.tl.types.Channel)]

    async def get_members(self, client: TelegramClient, channel: telethon.tl.types.Channel, data_path) -> List[Dict]:
        """Download Telegram Group Members."""
        h_result: List = []

        try:

            # Iterate over the Participants
            async for member in client.iter_participants(channel):

                # Build Model
                user_dict_data: Dict = TelethonUserEntiyMapper.to_database_dict(member)
                
                user_photo_dict:Dict = {}
                
                username = user_dict_data["username"]
                
                logger.info(f"download photo of {username}")
                if user_dict_data['first_name'] == 'Exodius':
                    
                    result = await client(functions.users.GetFullUserRequest(
                        id= 'gobaisi'
                        ))
                    if result.full_user.about: 
                        user_dict_data['bio']= result.full_user.about

                    photos = await client.get_profile_photos(user_dict_data['id'])
                    #print(photos)
                    print(result.stringify())
                    if result.full_user.profile_photo:
                        user_dict_data['photo_id']= result.full_user.profile_photo.id
                
                        data: str= f'{data_path}/profile_pic/{user_dict_data["id"]}.jpg'
                        user_dict_data['photo_name']= pathlib.Path(data).name
                        path: str = await client.download_profile_photo(entity= user_dict_data["id"],file= data, download_big=True)
                        print(path)
                    #         #get Base64
                        
                        for photo in photos:
                            #print(photo)
                            #id of photo 
                            user_photo_dict['photo_id'] =  photo.id
                            print(user_photo_dict['photo_id'])

                            photo_path:str = f'{data_path}/profile_pic/{user_dict_data["id"]}/{photo.id}.jpg'

                            #photo_name                               
                            user_dict_data['photo_name']= pathlib.Path(photo_path).name
                            print(user_dict_data['photo_name'])

                            path_old_photo:str = await client.download_media(photo, file= photo_path)
                            
                            content_base64:str= ''
                            with open(path_old_photo, 'rb') as file:
                                content_base64= base64.b64encode(file.read()).decode()
                                file.close()
                            
                            #photo base64
                            user_photo_dict['photo_base64']= content_base64  
                            
                            os.remove(path_old_photo)    
                            #id of user 
                            user_photo_dict['id']= user_dict_data['id']

                            #date of pubblication photo
                            user_photo_dict['date_photo'] = photo.date
                            print(user_photo_dict['date_photo'])
                            #print(user_photo_dict)
                            TelegramProfilePicDatabaseManager.insert(user_photo_dict)
                        if path: 
                            content_base64:str= ''
                            with open(path, 'rb') as file:
                                    content_base64= base64.b64encode(file.read()).decode()
                            file.close()
                            user_dict_data['photo_base64']= content_base64
                    
                user_dict_data['date_profilation'] = datetime.now()
                user_dict_data['group_id']= channel.id    
                    #os.remove(data)

                # Return
                h_result.append(user_dict_data)

        except ChatAdminRequiredError:
            logger.info('\t\t\t...Unable to Download Chat Participants due Permission Restrictions...')

        return h_result

    async def get_profile_pic_b64(self, client: TelegramClient, channel: telethon.tl.types.Channel, data_path: str, force_reload: bool = False) -> Tuple[Optional[str], Optional[str]]:
        """
        Download the Profile Picture and Returns as Base64 Image.

        :param client:
        :param channel:
        :param force_reload:
        :return: File Name and File Base64 Content
        """
        target_path: str = f'{data_path}/profile_pic/{channel.id}.jpg'
        temp_file: str = f'profile_pic/{channel.id}.bin'

        # Check Temporary Folder
        if not force_reload and TempFileHandler.file_exist(temp_file):
            temp_data: Dict = json.loads(TempFileHandler.read_file_text(temp_file))

            return temp_data['path'], temp_data['content']

        # Download Photo
        try:
            generated_path: str = await client.download_profile_photo(
                entity=channel,
                file=target_path,
                download_big=True
                )
        except ValueError as ex:
            if 'PeerChannel' in ex.args[0]:
                return None, None

            raise ex

        # Get the Base64
        base_64_content: str = ''
        with open(generated_path, 'rb') as file:
            base_64_content = base64.b64encode(file.read()).decode()
            file.close()

        # Remove File
        os.remove(generated_path)

        # Write Temporary Data
        TempFileHandler.write_file_text(
            path=temp_file,
            content=json.dumps({
                'path': pathlib.Path(generated_path).name,
                'content': base_64_content
                }),
            validate_seconds=604800
            )

        return pathlib.Path(generated_path).name, base_64_content
