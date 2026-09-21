"""Local end-to-end, batch, realtime, media, and persistence tests."""

import configparser
import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from telos_x.core.media_download_handling.photo_media_downloader import PhotoMediaDownloader
from telos_x.core.media_download_handling.std_media_downloader import StandardMediaDownloader
from telos_x.core.media_handler import UniversalTelegramMediaHandler
from telos_x.database.telegram_group_database import (
    TelegramGroupDatabaseManager,
    TelegramMessageDatabaseManager,
)
from telos_x.database.telegram_message_ai_analysis_database import (
    TelegramMessageAIAnalysisDatabaseManager,
)
from telos_x.models.database.telegram_db_model import TelegramMessageOrmEntity
from telos_x.modules.telegram_messages_listener import TelegramGroupMessageListener
from telos_x.modules.telegram_messages_scrapper import TelegramGroupMessageScrapper
from telos_x.services.message_processing import MessageProcessingService
from telos_x.services.traslation.schemas import TranslationResult


def _message(message_id=1, text='raw threat text', group_id=100):
    return SimpleNamespace(
        id=message_id,
        raw_text=text,
        message=text,
        date=datetime.datetime.now(datetime.timezone.utc),
        sender_id=7,
        from_id=SimpleNamespace(user_id=7),
        peer_id=SimpleNamespace(channel_id=group_id),
        reply_to_msg_id=None,
        reply_to=None,
        chat=None,
        voice=None,
        media=None,
    )


def _config(tmp_path, *, ai='false', translation='false'):
    config = configparser.ConfigParser(interpolation=None)
    config.read_dict(
        {
            'CONFIGURATION': {
                'phone_number': '+1000',
                'data_path': str(tmp_path),
            },
            'AI': {'enabled': ai, 'model_version': 'test-v1'},
            'TRANSLATION': {'enabled': translation},
            'FINDER': {'enabled': 'false'},
            'AI_ALERTING': {'enabled': 'false'},
        }
    )
    return config


class FakeTranslation:
    async def translate(self, text, **kwargs):
        return TranslationResult(
            original_text=text,
            translated_text='translated threat text',
            provider='fake',
            used_fallback=False,
            success=True,
        )


class FakeFinder:
    async def find_signals(self, message, **kwargs):
        return [
            {
                'id': 'test-rule',
                'notifiers': ['fake'],
                'response': None,
                'severity_hint': 'high',
            }
        ]


class FakeAI:
    def __init__(self, fail=False):
        self.fail = fail

    def analyze_message(self, text, signal_hits=None):
        if self.fail:
            raise RuntimeError('controlled AI failure')
        task = {
            'labels': ['attack_claim'],
            'scores': {'attack_claim': 0.9},
            'top_label': 'attack_claim',
            'top_score': 0.9,
            'source_model': 'controlled',
        }
        return {
            'activity': task,
            'attack_type': task,
            'target_nation': task,
            'meta': {
                'risk_score': 0.8,
                'severity': 'high',
                'escalated_to_bert': False,
                'alert_recommended': True,
            },
        }


class FakeNotifier:
    def __init__(self, fail=False):
        self.notifiers = {'fake': {'instance': object()}}
        self.calls = []
        self.fail = fail

    async def run(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError('controlled notifier failure')


@pytest.mark.asyncio
async def test_end_to_end_message_writes_raw_ai_and_notifies(
    database, group_values, tmp_path
):
    TelegramGroupDatabaseManager.insert_or_update(group_values())
    service = MessageProcessingService()
    service.translation_enabled = True
    service.translation_service = FakeTranslation()
    service.ai_enabled = True
    service.ai_analysis = FakeAI()
    service.finder = FakeFinder()
    service.notifier = FakeNotifier()
    service.config = _config(tmp_path)
    service.model_version = 'test-v1'

    result = await service.process_message(
        message=_message(),
        group_id=100,
        client=object(),
        data_path=str(tmp_path),
        download_media=False,
        target_phone_number='+1000',
        pipeline='test',
    )
    raw = database.scalar(select(TelegramMessageOrmEntity))
    ai = TelegramMessageAIAnalysisDatabaseManager.get_by_message(1, 100)
    assert raw.raw == 'raw threat text'
    assert raw.message == 'translated threat text'
    assert ai.top_activity == 'attack_claim'
    assert result['raw_saved'] and result['ai_saved']
    assert len(service.notifier.calls) == 1


@pytest.mark.asyncio
async def test_ai_and_notifier_failures_do_not_lose_raw_message(
    database, group_values, tmp_path
):
    TelegramGroupDatabaseManager.insert_or_update(group_values())
    service = MessageProcessingService()
    service.translation_enabled = False
    service.ai_enabled = True
    service.ai_analysis = FakeAI(fail=True)
    service.finder = FakeFinder()
    service.notifier = FakeNotifier(fail=True)
    service.config = _config(tmp_path)
    result = await service.process_message(
        message=_message(),
        group_id=100,
        client=object(),
        data_path=str(tmp_path),
        download_media=False,
        target_phone_number='+1000',
        pipeline='test',
    )
    assert TelegramMessageDatabaseManager.get_max_id_from_group(100) == 1
    assert result['raw_saved'] and result['ai_saved']


class FakeBatchClient:
    def __init__(self, messages):
        self.messages = messages
        self.calls = 0

    async def get_input_entity(self, group_id):
        return f'peer:{group_id}'

    async def iter_messages(self, peer, **kwargs):
        self.calls += 1
        if self.calls == 1:
            for message in self.messages:
                yield message


@pytest.mark.asyncio
async def test_batch_public_path_processes_messages(database, group_values, tmp_path):
    TelegramGroupDatabaseManager.insert_or_update(group_values())
    client = FakeBatchClient([_message(5, 'batch text')])
    args = {
        'download_messages': True,
        'group_id': '*',
        'ignore_media': True,
    }
    await TelegramGroupMessageScrapper().run(
        _config(tmp_path),
        args,
        {'telegram_client': client},
    )
    assert TelegramMessageDatabaseManager.get_max_id_from_group(100) == 5
    assert TelegramMessageAIAnalysisDatabaseManager.get_by_message(5, 100)


class FakeServiceMessage:
    def __init__(self, message_id):
        self.id = message_id


class FakePagedBatchClient:
    def __init__(self):
        self.minimum_ids = []

    async def get_input_entity(self, group_id):
        return f'peer:{group_id}'

    async def iter_messages(self, peer, **kwargs):
        del peer
        minimum_id = kwargs['min_id']
        self.minimum_ids.append(minimum_id)
        if minimum_id < 1:
            # The implementation checks Telethon's actual MessageService
            # class, so use a controlled subclass-free patch below.
            yield FakeServiceMessage(1)
        elif minimum_id == 1:
            yield _message(2, 'after service-only page')


@pytest.mark.asyncio
async def test_batch_pagination_advances_past_service_only_page(
    database, group_values, tmp_path, monkeypatch
):
    TelegramGroupDatabaseManager.insert_or_update(group_values())
    client = FakePagedBatchClient()
    monkeypatch.setattr(
        'telos_x.modules.telegram_messages_scrapper.MessageService',
        FakeServiceMessage,
    )
    await TelegramGroupMessageScrapper().run(
        _config(tmp_path),
        {'download_messages': True, 'group_id': '*', 'ignore_media': True},
        {'telegram_client': client},
    )
    assert client.minimum_ids == [-1, 1, 2]
    assert TelegramMessageDatabaseManager.get_max_id_from_group(100) == 2


class FakeListenerClient:
    def __init__(self):
        self.handlers = []

    def add_event_handler(self, handler, event_type):
        self.handlers.append((handler, event_type))

    async def catch_up(self):
        return None

    async def run_until_disconnected(self):
        return None


@pytest.mark.asyncio
async def test_realtime_public_registration_reaches_shared_pipeline(
    database, group_values, tmp_path
):
    TelegramGroupDatabaseManager.insert_or_update(group_values())
    client = FakeListenerClient()
    listener = TelegramGroupMessageListener()
    await listener.run(
        _config(tmp_path),
        {'listen': True, 'ignore_media': True, 'group_id': '*'},
        {'telegram_client': client},
    )
    event = SimpleNamespace(
        message=_message(9, 'realtime text'),
        chat=SimpleNamespace(id=100, title='Group 100'),
    )
    new_message_handler = client.handlers[0][0]
    await new_message_handler(event)
    assert TelegramMessageDatabaseManager.get_max_id_from_group(100) == 9
    assert TelegramMessageAIAnalysisDatabaseManager.get_by_message(9, 100)


class FakeDownloadMessage:
    def __init__(self, generated_path):
        self.generated_path = generated_path

    async def download_media(self, _target):
        return self.generated_path


@pytest.mark.asyncio
async def test_media_downloaders_create_directories_and_capture_extension(tmp_path):
    metadata = {'file_name': 'sample.pdf'}
    target = tmp_path / 'nested' / 'media'
    await StandardMediaDownloader.download(
        FakeDownloadMessage(str(target / 'sample.pdf')),
        metadata,
        str(target),
    )
    assert target.is_dir()
    assert metadata['extension'] == '.pdf'
    photo_target = tmp_path / 'photos'
    await PhotoMediaDownloader.download(
        FakeDownloadMessage(str(photo_target / 'photo.jpg')),
        {'file_name': 'photo.jpg'},
        str(photo_target),
    )
    assert photo_target.is_dir()


@pytest.mark.asyncio
async def test_non_media_message_is_safe(tmp_path):
    assert await UniversalTelegramMediaHandler().handle_medias(
        _message(), 100, str(tmp_path)
    ) is None
