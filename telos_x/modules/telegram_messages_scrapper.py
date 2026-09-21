"""Telegram Group Scrapper."""
import logging
from configparser import ConfigParser
import asyncio
from typing import Dict, List, cast

import telethon.errors.rpcerrorlist
from telethon import TelegramClient
from telethon.errors import RPCError
from telethon.tl.types import Message, MessageService


from telos_x.core.base_module import BaseModule
from telos_x.database.telegram_group_database import TelegramGroupDatabaseManager, TelegramMessageDatabaseManager
from telos_x.models.database.telegram_db_model import TelegramGroupOrmEntity
from telos_x.services.message_processing import MessageProcessingService


logger = logging.getLogger('TelegramExplorer')


class TelegramGroupMessageScrapper(BaseModule):
    """Download all Messages from Telegram Groups."""

    def __init__(self) -> None:
        """Class Initializer."""
        self.processor = MessageProcessingService()

    async def can_activate(self, config: ConfigParser, args: Dict, data: Dict) -> bool:
        """
        Abstract Method for Module Activation Function.

        :return:
        """
        return cast(bool, args['download_messages'])

    async def run(self, config: ConfigParser, args: Dict, data: Dict) -> None:
        """Execute Module."""
        if not await self.can_activate(config, args, data):
            logger.debug('\t\tModule is Not Enabled...')
            return

        # Get Client
        client: TelegramClient = data['telegram_client']

        self.processor.configure(config)
        # Load Groups from DB
        groups: List[TelegramGroupOrmEntity] = TelegramGroupDatabaseManager.get_all_by_phone_number(
            config['CONFIGURATION']['phone_number'])
        logger.info(f'\t\tFound {len(groups)} Groups')

        # Filter Groups
        if args['group_id'] and args['group_id'] != '*':
            group_ids: List[int] = [int(group_id) for group_id in args['group_id'].split(',')]
            groups = [group for group in groups if group.id in group_ids]

            logger.info(f'\t\tApplied Groups Filtering... {len(groups)} remaining')

        for group in groups:
            try:
                await self.__download_messages(
                    group_id=group.id,
                    client=client,
                    group_name=group.title,
                    download_media=not args['ignore_media'],
                    data_path=config['CONFIGURATION']['data_path'],
                    target_phone_number=config['CONFIGURATION']['phone_number'],
                )
            except ValueError as ex:
                logger.info('\t\t\tUnable to Download Messages...')
                logger.error(ex)
            except telethon.errors.rpcerrorlist.ChannelPrivateError as ex:
                logger.info('\t\t\tUnable to Download dua a Channel Private Error Restriction...')
                logger.error(ex)
            except RPCError:
                logger.exception(
                    'Unable to download messages for group %s; continuing',
                    group.id,
                )
            except Exception:
                logger.exception(
                    'Unexpected group-level message download failure for %s; '
                    'continuing with the remaining groups',
                    group.id,
                )

    async def __download_messages(self, group_id: int, group_name: str, client: TelegramClient, download_media: bool, data_path: str, target_phone_number: str) -> None:  # pylint: disable=R0913
        """Download all Messages from a Single Group."""
        peer = await client.get_input_entity(group_id)
        # Keep a Telegram pagination cursor independent of DB persistence.
        # Service messages are intentionally not stored, but their IDs still
        # need to advance the cursor so they cannot hide later normal messages.
        page_min_id: int = (
            TelegramMessageDatabaseManager.get_max_id_from_group(group_id)
            or -1
        )

        # Main Download Loop
        while True:

            # Loop Control
            records_seen: int = 0

            # Log
            logger.info(
                '\t\tDownload Messages from "%s" > Last Offset: %s',
                group_name,
                page_min_id,
            )

            # Wait to Prevent Telegram Flood Detection
            await asyncio.sleep(1)

            # Get all Chats from a Single Group
            # https://docs.telethon.dev/en/latest/modules/client.html#telethon.client.messages.MessageMethods.iter_messages
            async for message in client.iter_messages(
                    peer,
                    reverse=True,
                    limit=500,
                    min_id=page_min_id,
                    ):

                records_seen += 1
                message_id = getattr(message, 'id', None)
                if message_id is not None:
                    page_min_id = max(page_min_id, int(message_id))

                # Ignore MessageService Messages
                if isinstance(message, MessageService):
                    continue

                # Handle Unknown Types
                if not isinstance(message, Message):
                    logger.debug(f'\t\t{type(message)}')

                if message.reply_to is not None:
                    pass

                if message.reply_to_msg_id:
                    pass
                
                try:
                    await self.processor.process_message(
                        message=message,
                        group_id=group_id,
                        client=client,
                        data_path=data_path,
                        download_media=download_media,
                        target_phone_number=target_phone_number,
                        pipeline="batch",
                        chat=None,
                        event=None,
                    )
                except Exception:
                    logger.exception(
                        'Unexpected failure processing message %s in group %s; '
                        'continuing',
                        getattr(message, 'id', 'unknown'),
                        group_id,
                    )
                
            # Exit Rule
            if records_seen == 0:
                break
