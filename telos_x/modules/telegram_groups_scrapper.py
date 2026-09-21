"""Telegram group scraper."""

import asyncio
import base64
import csv
import json
import logging
import os
import pathlib
import random
import re
from configparser import ConfigParser
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union, cast

import telethon.tl.types
from telethon import TelegramClient, functions
from telethon.errors import (
    ChannelPrivateError,
    ChatAdminRequiredError,
    InviteRequestSentError,
    RPCError,
)
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.types import Channel, Chat, ChatPhoto

from telos_x.core.base_module import BaseModule
from telos_x.core.mapper.telethon_channel_mapper import TelethonChannelEntityMapper
from telos_x.core.mapper.telethon_user_mapper import TelethonUserEntiyMapper
from telos_x.core.temp_file import TempFileHandler
from telos_x.database.telegram_group_database import (
    TelegramGroupDatabaseManager,
    TelegramProfilePicDatabaseManager,
    TelegramUserDatabaseManager,
)
from telos_x.models.database.telegram_db_model import TelegramGroupOrmEntity
from telos_x.paths import DEFAULT_GROUPS_FILE, PROJECT_ROOT


logger = logging.getLogger('TelegramExplorer')


class TelegramGroupScrapper(BaseModule):
    """List all groups on the configured Telegram account."""

    _GROUP_LINK_PATTERN = re.compile(
        r"(?:https?://)?(?:t|telegram)\.(?:me|dog)/(joinchat/|\+)?([\w-]+)",
        re.IGNORECASE,
    )

    async def can_activate(
        self,
        config: ConfigParser,
        args: Dict,
        data: Dict,
    ) -> bool:
        """Return whether group loading was requested."""
        return cast(bool, args['load_groups'])

    async def run(self, config: ConfigParser, args: Dict, data: Dict) -> None:
        """Load configured groups, their metadata, and their members."""
        if not await self.can_activate(config, args, data):
            logger.debug('\t\tModule is Not Enabled...')
            return

        data.setdefault('groups', {})
        data.setdefault('members', {})

        client: TelegramClient = data['telegram_client']
        phone_number = config['CONFIGURATION']['phone_number']
        data_path = config['CONFIGURATION']['data_path']
        db_groups: List[TelegramGroupOrmEntity] = (
            TelegramGroupDatabaseManager.get_all_by_phone_number(phone_number)
        )

        await self._join_configured_groups(
            client=client,
            group_references=self._load_group_links(config),
            known_usernames=[group.group_username for group in db_groups],
        )

        chats = await self.load_groups(client=client)
        self._write_group_status_file(chats, db_groups, data_path)

        for chat in chats:
            try:
                await self._process_group(
                    client=client,
                    chat=chat,
                    phone_number=phone_number,
                    data_path=data_path,
                    config=config,
                    refresh_profile_photos=args.get(
                        'refresh_profile_photos', False
                    ),
                )
            except (ChannelPrivateError, ChatAdminRequiredError, RPCError, ValueError):
                logger.exception(
                    'Unable to process Telegram group %s; continuing with the batch',
                    getattr(chat, 'id', 'unknown'),
                )
            except Exception:
                logger.exception(
                    'Unexpected failure processing Telegram group %s; '
                    'continuing with the batch',
                    getattr(chat, 'id', 'unknown'),
                )

    async def _process_group(
        self,
        *,
        client: TelegramClient,
        chat: Union[Channel, Chat],
        phone_number: str,
        data_path: str,
        config: ConfigParser,
        refresh_profile_photos: bool,
    ) -> None:
        """Persist one group, all exposed members, and selected profiles."""
        logger.info(
            '\t\tProcessing "%s (%s)" Members and Group Profile Picture',
            chat.title,
            chat.id,
        )
        await self._log_linked_discussion_group(client, chat)

        values = TelethonChannelEntityMapper.to_database_dict(
            entity=chat,
            target_phone_numer=phone_number,
        )
        if chat.photo is not None and isinstance(chat.photo, ChatPhoto):
            values['photo_id'] = chat.photo.photo_id
            photo_name, photo_base64 = await self.get_profile_pic_b64(
                client=client,
                channel=chat,
                data_path=data_path,
                force_reload=refresh_profile_photos,
            )
            values['photo_base64'] = photo_base64
            values['photo_name'] = photo_name
        else:
            values['photo_id'] = None
            values['photo_base64'] = None
            values['photo_name'] = None

        # Required FK ordering: the group is committed before membership.
        TelegramGroupDatabaseManager.insert_or_update(values)

        members = await self.get_members(
            client=client,
            channel=chat,
            data_path=data_path,
        )
        TelegramUserDatabaseManager.insert_or_update_batch(members)
        await self._profile_selected_users(
            client=client,
            members=members,
            data_path=data_path,
            config=config,
        )

    @staticmethod
    def _project_root() -> pathlib.Path:
        """Return the directory containing the project package and config."""
        return PROJECT_ROOT

    def _resolve_groups_file(self, config: ConfigParser) -> pathlib.Path:
        """Resolve CONFIGURATION.groups_file with a project-root fallback."""
        configured_path = config.get(
            'CONFIGURATION',
            'groups_file',
            fallback='',
        ).strip()
        if not configured_path:
            return DEFAULT_GROUPS_FILE

        groups_file = pathlib.Path(configured_path).expanduser()
        if not groups_file.is_absolute():
            groups_file = self._project_root() / groups_file
        return groups_file.resolve()

    def _load_group_links(self, config: ConfigParser) -> List[str]:
        """Load discovery group references without depending on the CWD."""
        groups_file = self._resolve_groups_file(config)
        if not groups_file.exists():
            logger.warning(
                'Telegram groups discovery file not found: %s. '
                'No new groups will be joined.',
                groups_file,
            )
            return []

        try:
            with groups_file.open('r', encoding='utf-8-sig', newline='') as stream:
                reader = csv.DictReader(stream)
                if not reader.fieldnames or 'telegram_group' not in reader.fieldnames:
                    logger.error(
                        'Telegram groups discovery file %s must contain a '
                        'telegram_group column.',
                        groups_file,
                    )
                    return []
                return [
                    row['telegram_group'].strip()
                    for row in reader
                    if row.get('telegram_group') and row['telegram_group'].strip()
                ]
        except (OSError, csv.Error) as exc:
            logger.error('Unable to read groups file %s: %s', groups_file, exc)
            return []

    async def _join_configured_groups(
        self,
        client: TelegramClient,
        group_references: List[str],
        known_usernames: List[str],
    ) -> None:
        """Join public usernames or private invite links from ``groups.csv``."""
        known = {
            username.lstrip('@').casefold()
            for username in known_usernames
            if username
        }

        for reference in group_references:
            match = self._GROUP_LINK_PATTERN.search(reference)
            invite_prefix: Optional[str] = None
            target: Optional[str] = None
            if match:
                invite_prefix, target = match.groups()
            elif re.fullmatch(r'@?[\w-]+', reference):
                target = reference.lstrip('@')

            if not target:
                logger.warning('Ignoring invalid Telegram group reference: %s', reference)
                continue
            if not invite_prefix and target.casefold() in known:
                continue

            await asyncio.sleep(random.randint(1, 3))
            try:
                if invite_prefix:
                    await client(ImportChatInviteRequest(target))
                else:
                    await client(JoinChannelRequest(target))
                    known.add(target.casefold())
                logger.info('Telegram account joined group reference %s', reference)
            except InviteRequestSentError:
                logger.info('Join request submitted for Telegram group %s', reference)
            except (ChannelPrivateError, RPCError, ValueError) as exc:
                logger.warning('Unable to join Telegram group %s: %s', reference, exc)

    @staticmethod
    async def _log_linked_discussion_group(
        client: TelegramClient,
        chat: Union[Channel, Chat],
    ) -> None:
        if not isinstance(chat, Channel) or not chat.username:
            return
        try:
            full = await client(functions.channels.GetFullChannelRequest(chat.id))
            linked_chat_id = full.full_chat.linked_chat_id
            if linked_chat_id:
                linked_group = next(
                    (candidate for candidate in full.chats if candidate.id == linked_chat_id),
                    None,
                )
                if linked_group is not None:
                    logger.debug(
                        'Linked discussion group for %s: %s',
                        chat.id,
                        linked_group.username,
                    )
        except (RPCError, ValueError) as exc:
            logger.debug('Unable to resolve linked discussion group %s: %s', chat.id, exc)

    @staticmethod
    def _write_group_status_file(
        chats: List[Union[Channel, Chat]],
        db_groups: List[TelegramGroupOrmEntity],
        data_path: str,
    ) -> None:
        """Preserve the operational monitored/deleted group status output."""
        chat_ids = {chat.id for chat in chats}
        deleted_titles = [
            group.title
            for group in db_groups
            if group.id not in chat_ids
        ]
        status_path = pathlib.Path(data_path) / 'not_active_group.txt'
        status_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with status_path.open('w', encoding='utf-8') as stream:
                stream.write('Gruppi che non sono piu monitorati:\n')
                stream.write('\n'.join(deleted_titles))
                stream.write('\nGruppi monitorati dalla sonda:\n')
                stream.write('\n'.join(chat.title for chat in chats))
        except OSError as exc:
            logger.warning('Unable to write group status file %s: %s', status_path, exc)

    async def load_groups(
        self,
        client: TelegramClient,
    ) -> List[Union[Channel, Chat]]:
        """Load every channel and basic chat visible to the account."""
        logger.info('\t\tEnumerating Groups')
        groups: List[Union[Channel, Chat]] = []
        async for dialog in client.iter_dialogs(limit=None):
            entity = getattr(dialog, 'entity', None)
            if isinstance(entity, (Channel, Chat)):
                groups.append(entity)
        return groups

    async def get_members(
        self,
        client: TelegramClient,
        channel: Union[Channel, Chat],
        data_path: str,
    ) -> List[Dict]:
        """Return lightweight member profiles for a Telegram group."""
        del data_path  # Kept in the public signature for caller compatibility.
        members: List[Dict] = []
        try:
            async for member in client.iter_participants(channel, limit=None):
                user_values = TelethonUserEntiyMapper.to_database_dict(member)
                user_values['bio'] = None
                user_values['date_profilation'] = None
                user_values['group_id'] = channel.id
                members.append(user_values)
        except ChatAdminRequiredError:
            logger.info(
                '\t\t\t...Unable to Download Chat Participants '
                'due Permission Restrictions...'
            )
        retrieved = len(members)
        expected = getattr(channel, 'participants_count', None)
        logger.info('Retrieved %s members from group %s', retrieved, channel.id)
        if expected is not None and expected > retrieved:
            logger.warning(
                'Telegram exposed %s/%s participants for group %s. '
                'Participant enumeration may be limited by Telegram.',
                retrieved,
                expected,
                channel.id,
            )
        return members

    @staticmethod
    def _parse_profiling_values(value: str, strip_at: bool = False) -> set[str]:
        """Parse comma/whitespace separated configuration values."""
        parsed = set()
        for item in re.split(r'[\s,]+', value):
            normalized = item.strip()
            if not normalized:
                continue
            if strip_at:
                normalized = normalized.lstrip('@')
            parsed.add(normalized.casefold())
        return parsed

    def should_profile_user(
        self,
        user_dict_data: Dict,
        config: ConfigParser,
    ) -> bool:
        """Return whether an observed user is eligible for extended profiling."""
        if not config.getboolean('PROFILING', 'enabled', fallback=False):
            return False
        if config.getboolean('PROFILING', 'profile_all_users', fallback=False):
            return True

        target_usernames = self._parse_profiling_values(
            config.get('PROFILING', 'target_usernames', fallback=''),
            strip_at=True,
        )
        target_first_names = self._parse_profiling_values(
            config.get('PROFILING', 'target_first_names', fallback=''),
        )
        username = str(user_dict_data.get('username') or '').lstrip('@').casefold()
        first_name = str(user_dict_data.get('first_name') or '').casefold()
        return username in target_usernames or first_name in target_first_names

    async def _profile_selected_users(
        self,
        client: TelegramClient,
        members: List[Dict],
        data_path: str,
        config: ConfigParser,
    ) -> None:
        """Download and persist extended data only for configured targets."""
        for user_values in members:
            if not self.should_profile_user(user_values, config):
                continue
            try:
                await self._profile_user(client, user_values, data_path)
                TelegramUserDatabaseManager.insert_or_update(user_values)
            except Exception:  # A target failure must not discard light profiles.
                logger.exception(
                    'Unable to complete extended Telegram profile for user %s',
                    user_values.get('id'),
                )

    async def _profile_user(
        self,
        client: TelegramClient,
        user_values: Dict,
        data_path: str,
    ) -> None:
        """Populate bio and profile pictures for one selected user."""
        user_id = user_values['id']
        full_result = await client(
            functions.users.GetFullUserRequest(id=user_id)
        )
        user_values['bio'] = full_result.full_user.about
        user_values['date_profilation'] = datetime.now()

        profile_photo = full_result.full_user.profile_photo
        if profile_photo:
            user_values['photo_id'] = profile_photo.id
            current_path = pathlib.Path(data_path) / 'profile_pic' / f'{user_id}.jpg'
            current_path.parent.mkdir(parents=True, exist_ok=True)
            generated_path = await client.download_profile_photo(
                entity=user_id,
                file=str(current_path),
                download_big=True,
            )
            if generated_path:
                generated = pathlib.Path(generated_path)
                try:
                    user_values['photo_name'] = generated.name
                    user_values['photo_base64'] = base64.b64encode(
                        generated.read_bytes()
                    ).decode()
                finally:
                    generated.unlink(missing_ok=True)

        photos = await client.get_profile_photos(user_id)
        for photo in photos:
            photo_path = (
                pathlib.Path(data_path)
                / 'profile_pic'
                / str(user_id)
                / f'{photo.id}.jpg'
            )
            photo_path.parent.mkdir(parents=True, exist_ok=True)
            downloaded_path = await client.download_media(photo, file=str(photo_path))
            if not downloaded_path:
                continue
            downloaded = pathlib.Path(downloaded_path)
            try:
                TelegramProfilePicDatabaseManager.insert(
                    {
                        'photo_id': photo.id,
                        'photo_base64': base64.b64encode(
                            downloaded.read_bytes()
                        ).decode(),
                        'photo_name': downloaded.name,
                        'id': user_id,
                        'date_photo': photo.date,
                    }
                )
            finally:
                downloaded.unlink(missing_ok=True)

    async def get_profile_pic_b64(
        self,
        client: TelegramClient,
        channel: Union[Channel, Chat],
        data_path: str,
        force_reload: bool = False,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Download a group profile picture and return name plus base64 data."""
        target_path = os.path.join(data_path, 'profile_pic', f'{channel.id}.jpg')
        temp_file = f'profile_pic/{channel.id}.bin'

        if not force_reload and TempFileHandler.file_exist(temp_file):
            temp_data: Dict = json.loads(TempFileHandler.read_file_text(temp_file))
            return temp_data['path'], temp_data['content']

        pathlib.Path(target_path).parent.mkdir(parents=True, exist_ok=True)
        try:
            generated_path = await client.download_profile_photo(
                entity=channel,
                file=target_path,
                download_big=True,
            )
        except ValueError as exc:
            if exc.args and 'PeerChannel' in str(exc.args[0]):
                return None, None
            raise
        if not generated_path:
            return None, None

        generated = pathlib.Path(generated_path)
        try:
            base_64_content = base64.b64encode(generated.read_bytes()).decode()
        finally:
            generated.unlink(missing_ok=True)

        TempFileHandler.write_file_text(
            path=temp_file,
            content=json.dumps(
                {
                    'path': generated.name,
                    'content': base_64_content,
                }
            ),
            validate_seconds=604800,
        )
        return generated.name, base_64_content
