"""Mocked Telegram discovery, enumeration, and participant integration tests."""

import configparser
import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.types import Channel, Chat, ChatPhotoEmpty, User

from telos_x.database.telegram_group_database import TelegramUserDatabaseManager
from telos_x.models.database.telegram_db_model import (
    TelegramUserGroupOrmEntity,
    TelegramUserOrmEntity,
)
from telos_x.modules.telegram_groups_scrapper import TelegramGroupScrapper
from telos_x.paths import DEFAULT_GROUPS_FILE


def _channel(group_id, title, count, username=None):
    return Channel(
        id=group_id,
        title=title,
        photo=ChatPhotoEmpty(),
        date=datetime.datetime.now(datetime.timezone.utc),
        access_hash=group_id * 10,
        username=username,
        megagroup=True,
        participants_count=count,
    )


def _chat(group_id, title, count):
    return Chat(
        id=group_id,
        title=title,
        photo=ChatPhotoEmpty(),
        participants_count=count,
        date=datetime.datetime.now(datetime.timezone.utc),
        version=1,
    )


def _user(user_id, username):
    return User(id=user_id, username=username, first_name=username.title())


class FakeScrapingClient:
    def __init__(self, groups=None, participants=None):
        self.groups = groups or []
        self.participants = participants or {}
        self.participant_limits = []
        self.requests = []
        self.full_user_ids = []

    async def iter_dialogs(self, limit=None):
        assert limit is None
        for entity in self.groups:
            yield SimpleNamespace(entity=entity)

    async def iter_participants(self, channel, limit=None):
        self.participant_limits.append(limit)
        for user in self.participants.get(channel.id, []):
            yield user

    async def __call__(self, request):
        self.requests.append(request)
        if isinstance(request, JoinChannelRequest) and request.channel == 'bad':
            raise ValueError('inaccessible')
        if request.__class__.__name__ == 'GetFullUserRequest':
            self.full_user_ids.append(request.id)
            return SimpleNamespace(
                full_user=SimpleNamespace(about='extended bio', profile_photo=None)
            )
        return SimpleNamespace()

    async def get_profile_photos(self, _user_id):
        return []


def _profiling_config(tmp_path, **overrides):
    profiling = {
        'enabled': 'false',
        'profile_all_users': 'false',
        'target_usernames': '',
        'target_first_names': '',
    }
    profiling.update(overrides)
    config = configparser.ConfigParser()
    config.read_dict(
        {
            'CONFIGURATION': {
                'phone_number': '+1000',
                'data_path': str(tmp_path),
            },
            'PROFILING': profiling,
        }
    )
    return config


@pytest.mark.asyncio
async def test_iter_dialogs_returns_channel_and_basic_chat():
    channel = _channel(10, 'Channel', 0)
    chat = _chat(20, 'Chat', 0)
    client = FakeScrapingClient([channel, User(id=99), chat])
    assert await TelegramGroupScrapper().load_groups(client) == [channel, chat]


def test_default_groups_file_is_the_repository_root_file(tmp_path):
    config = _profiling_config(tmp_path)
    assert TelegramGroupScrapper()._resolve_groups_file(config) == DEFAULT_GROUPS_FILE


@pytest.mark.asyncio
async def test_all_exposed_participants_requested_and_gap_logged(tmp_path, caplog):
    channel = _channel(10, 'Channel', 3)
    client = FakeScrapingClient(participants={10: [_user(1, 'one'), _user(2, 'two')]})
    members = await TelegramGroupScrapper().get_members(client, channel, str(tmp_path))
    assert [member['id'] for member in members] == [1, 2]
    assert client.participant_limits == [None]
    assert 'exposed 2/3 participants' in caplog.text


@pytest.mark.asyncio
async def test_group_csv_formats_join_independently(tmp_path):
    groups_file = tmp_path / 'groups.csv'
    groups_file.write_text(
        'telegram_group\n'
        'https://t.me/public_one\n'
        't.me/+invitehash\n'
        '@public_two\n'
        'bad\n'
        'not a telegram reference\n',
        encoding='utf-8',
    )
    config = _profiling_config(tmp_path)
    config['CONFIGURATION']['groups_file'] = str(groups_file)
    scraper = TelegramGroupScrapper()
    references = scraper._load_group_links(config)
    client = FakeScrapingClient()
    with patch(
        'telos_x.modules.telegram_groups_scrapper.asyncio.sleep',
        new=AsyncMock(),
    ):
        await scraper._join_configured_groups(client, references, [])
    assert any(isinstance(request, ImportChatInviteRequest) for request in client.requests)
    assert sum(isinstance(request, JoinChannelRequest) for request in client.requests) == 3


@pytest.mark.asyncio
async def test_group_a_b_users_are_stored_once_with_all_memberships(
    database, tmp_path
):
    group_a = _channel(10, 'Group A', 3)
    group_b = _chat(20, 'Group B', 2)
    client = FakeScrapingClient(
        participants={
            10: [_user(1, 'user1'), _user(2, 'user2'), _user(3, 'user3')],
            20: [_user(2, 'user2'), _user(4, 'user4')],
        }
    )
    scraper = TelegramGroupScrapper()
    config = _profiling_config(tmp_path)
    for group in (group_a, group_b):
        await scraper._process_group(
            client=client,
            chat=group,
            phone_number='+1000',
            data_path=str(tmp_path),
            config=config,
            refresh_profile_photos=False,
        )

    assert database.scalar(select(func.count()).select_from(TelegramUserOrmEntity)) == 4
    assert database.scalar(
        select(func.count()).select_from(TelegramUserGroupOrmEntity)
    ) == 5
    assert TelegramUserDatabaseManager.get_group_ids_by_user_id(2) == [10, 20]


@pytest.mark.asyncio
async def test_selective_profile_stores_everyone_but_profiles_only_target(
    database, tmp_path
):
    group = _channel(10, 'Group A', 2)
    client = FakeScrapingClient(
        participants={10: [_user(1, 'normal_user'), _user(2, 'target_user')]}
    )
    config = _profiling_config(
        tmp_path,
        enabled='true',
        target_usernames='TARGET_USER',
    )
    await TelegramGroupScrapper()._process_group(
        client=client,
        chat=group,
        phone_number='+1000',
        data_path=str(tmp_path),
        config=config,
        refresh_profile_photos=False,
    )
    assert database.scalar(select(func.count()).select_from(TelegramUserOrmEntity)) == 2
    assert database.scalar(
        select(func.count()).select_from(TelegramUserGroupOrmEntity)
    ) == 2
    assert client.full_user_ids == [2]
    assert TelegramUserDatabaseManager.get_by_id(2).bio == 'extended bio'
