"""Operational utilities, reports, graph, maintenance, and notifier tests."""

import configparser
import datetime
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import inspect, select

from telos_x.database.db_initializer import DbInitializer
from telos_x.database.db_manager import DbManager
from telos_x.database.telegram_group_database import (
    TelegramGroupDatabaseManager,
    TelegramMediaDatabaseManager,
    TelegramMessageDatabaseManager,
    TelegramUserDatabaseManager,
)
from telos_x.database.telegram_message_ai_analysis_database import (
    TelegramMessageAIAnalysisDatabaseManager,
)
from telos_x.core.state_file import StateFileHandler
from telos_x.models.database.telegram_db_model import TelegramMessageOrmEntity
from telos_x.modules.telegram_connection_manager import TelegramConnector
from telos_x.modules.state_file_handler import SaveStateFileHandler
from telos_x.modules.telegram_graph_group_interaction import TelegramGraphGroupInteraction
from telos_x.modules.telegram_groups_list import TelegramGroupList
from telos_x.modules.telegram_maintenance.telegram_purge_old_data import (
    TelegramMaintenancePurgeOldData,
)
from telos_x.modules.telegram_report_generator.telegram_export_file_generator import (
    TelegramExportFileGenerator,
)
from telos_x.modules.telegram_report_generator.telegram_export_text_generator import (
    TelegramExportTextGenerator,
)
from telos_x.modules.telegram_report_generator.telegram_html_report_generator import (
    TelegramReportGenerator,
)
from telos_x.modules.telegram_report_generator.telegram_report_sent_telegram import (
    TelegramReportSentViaTelegram,
)
from telos_x.modules.telegram_stats_generator import TelegramStatsGenerator
from telos_x.notifier.discord_notifier import DiscordNotifier
from telos_x.notifier.notifier_engine import NotifierEngine
from telos_x.notifier.slack_notifier import SlackNotifier


def _config(tmp_path):
    config = configparser.ConfigParser(interpolation=None)
    config.read_dict(
        {
            'CONFIGURATION': {
                'phone_number': '+1000',
                'data_path': str(tmp_path),
                'api_id': '12345',
                'api_hash': 'placeholder-hash',
            }
        }
    )
    return config


def _message_values(message_id, group_id, date_time, text='message', from_id=1):
    return {
        'id': message_id,
        'group_id': group_id,
        'media_id': None,
        'date_time': date_time,
        'message': text,
        'raw': text,
        'from_id': from_id,
        'from_type': 'user',
        'to_id': group_id,
        'is_reply': False,
        'reply_to_msg_id': None,
    }


def _ai_values(message_id, group_id):
    return {
        'message_id': message_id,
        'group_id': group_id,
        'activity_json': '{}',
        'attack_type_json': '{}',
        'target_nation_json': '{}',
        'top_activity': None,
        'top_activity_score': None,
        'top_attack_type': None,
        'top_attack_type_score': None,
        'top_target_nation': None,
        'top_target_nation_score': None,
        'model_version': 'test',
        'created_at': datetime.datetime.now(datetime.timezone.utc),
        'risk_score': 0,
        'severity': 'low',
        'escalated_to_bert': False,
        'rule_hits_json': '[]',
        'alert_recommended': False,
    }


def test_fresh_db_initializer_creates_complete_schema(tmp_path):
    DbInitializer.init(str(tmp_path / 'new-data'))
    tables = set(inspect(DbManager.SQLALCHEMY_BINDS['data']).get_table_names())
    assert {
        'telegram_group',
        'telegram_user',
        'telegram_user_group',
        'telegram_message',
        'telegram_message_ai_analysis',
    }.issubset(tables)
    for session in DbManager.SESSIONS.values():
        session.close()
    for engine in DbManager.SQLALCHEMY_BINDS.values():
        engine.dispose()


@pytest.mark.asyncio
async def test_html_report_uses_packaged_templates_and_preserves_folder(
    database, group_values, user_values, tmp_path
):
    TelegramGroupDatabaseManager.insert_or_update(group_values())
    TelegramUserDatabaseManager.insert_or_update(user_values(1, 100))
    TelegramMessageDatabaseManager.insert(
        _message_values(
            1,
            100,
            datetime.datetime.now(datetime.timezone.utc),
            'report message',
        )
    )
    report_dir = tmp_path / 'reports'
    report_dir.mkdir()
    sentinel = report_dir / 'keep.txt'
    sentinel.write_text('keep', encoding='utf-8')
    args = {
        'report': True,
        'report_folder': str(report_dir),
        'group_id': '*',
        'filter': None,
        'limit_days': 30,
        'order_desc': False,
        'around_messages': 1,
        'suppress_repeating_messages': False,
    }
    await TelegramReportGenerator().run(_config(tmp_path), args, {})
    assert (report_dir / 'index.html').is_file()
    assert (report_dir / 'result_group_100_100.html').is_file()
    assert sentinel.read_text(encoding='utf-8') == 'keep'


@pytest.mark.asyncio
async def test_text_export_generates_filtered_output(
    database, group_values, tmp_path
):
    TelegramGroupDatabaseManager.insert_or_update(group_values())
    TelegramMessageDatabaseManager.insert(
        _message_values(
            1,
            100,
            datetime.datetime.now(datetime.timezone.utc),
            'report indicator',
        )
    )
    export_dir = tmp_path / 'text-export'
    await TelegramExportTextGenerator().run(
        _config(tmp_path),
        {
            'export_text': True,
            'report_folder': str(export_dir),
            'group_id': '*',
            'regex': 'indicator',
            'limit_days': 30,
            'order_desc': False,
        },
        {},
    )
    output = export_dir / 'result_group_100_100.txt'
    assert output.read_text(encoding='utf-8').strip() == 'indicator'


@pytest.mark.asyncio
async def test_file_export_copies_matching_media(
    database, group_values, tmp_path
):
    TelegramGroupDatabaseManager.insert_or_update(group_values())
    media_dir = tmp_path / 'media' / '100'
    media_dir.mkdir(parents=True)
    source = media_dir / 'sample.bin'
    source.write_bytes(b'telos-x-media')
    TelegramMediaDatabaseManager.insert(
        {
            'group_id': 100,
            'telegram_id': 7,
            'file_name': source.name,
            'extension': '.bin',
            'height': None,
            'width': None,
            'date_time': datetime.datetime.now(datetime.timezone.utc),
            'mime_type': 'application/octet-stream',
            'size_bytes': source.stat().st_size,
            'title': None,
            'name': None,
        }
    )
    export_dir = tmp_path / 'file-export'
    await TelegramExportFileGenerator().run(
        _config(tmp_path),
        {
            'export_file': True,
            'report_folder': str(export_dir),
            'group_id': '*',
            'filter': '*',
            'mime_type': '*',
            'limit_days': 30,
        },
        {},
    )
    assert (export_dir / '100_sample.bin').read_bytes() == b'telos-x-media'


@pytest.mark.asyncio
async def test_telegram_report_sender_packages_and_sends_with_mock(tmp_path):
    report_dir = tmp_path / 'send-report'
    report_dir.mkdir()
    (report_dir / 'index.html').write_text('report', encoding='utf-8')
    client = SimpleNamespace(
        get_input_entity=AsyncMock(return_value='receiver'),
        send_message=AsyncMock(),
        send_file=AsyncMock(),
    )
    with patch(
        'telos_x.modules.telegram_report_generator.telegram_report_sent_telegram.asyncio.sleep',
        new=AsyncMock(),
    ):
        await TelegramReportSentViaTelegram().run(
            _config(tmp_path),
            {
                'sent_report_telegram': True,
                'report_folder': str(report_dir),
                'attachment_name': 'audit_@@now@@',
                'destination_username': 'test_receiver',
                'title': 'Audit @@now@@',
            },
            {'telegram_client': client},
        )
    client.send_message.assert_awaited_once()
    client.send_file.assert_awaited_once()
    assert not list(report_dir.glob('audit_*.zip'))


@pytest.mark.asyncio
async def test_stats_report_handles_empty_database(database, tmp_path):
    report_dir = tmp_path / 'stats'
    await TelegramStatsGenerator().run(
        _config(tmp_path),
        {'stats': True, 'report_folder': str(report_dir), 'limit_days': 0},
        {},
    )
    contents = (report_dir / 'stats.txt').read_text(encoding='utf-8')
    assert 'Total Groups      : 0' in contents


@pytest.mark.asyncio
async def test_list_groups_handles_empty_database(database, tmp_path):
    data = {}
    await TelegramGroupList().run(
        _config(tmp_path),
        {'list_groups': True},
        data,
    )
    assert data == {'groups': {}, 'members': {}}


def test_graph_uses_many_to_many_membership_api(
    database, group_values, user_values, tmp_path
):
    TelegramGroupDatabaseManager.insert_or_update(group_values(title='Graph Group'))
    TelegramUserDatabaseManager.insert_or_update_batch(
        [user_values(1, 100), user_values(2, 100)]
    )
    TelegramMessageDatabaseManager.insert(
        _message_values(
            1,
            100,
            datetime.datetime.now(datetime.timezone.utc),
            from_id=1,
        )
    )
    group = TelegramGroupDatabaseManager.get_by_id(100)
    graph = TelegramGraphGroupInteraction.build_graph(group)
    assert {'group:100', 'user:1', 'user:2'}.issubset(graph.nodes)
    assert graph['user:1']['group:100']['interactions'] == 1
    output = tmp_path / 'graph.png'
    TelegramGraphGroupInteraction.draw_graph(graph, group.title, output)
    assert output.is_file() and output.stat().st_size > 0


@pytest.mark.asyncio
async def test_database_maintenance_deletes_old_media_ai_and_messages(
    database, group_values, tmp_path
):
    TelegramGroupDatabaseManager.insert_or_update(group_values())
    old = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=10)
    new = datetime.datetime.now(datetime.timezone.utc)
    TelegramMessageDatabaseManager.insert(_message_values(1, 100, old))
    TelegramMessageDatabaseManager.insert(_message_values(2, 100, new))
    TelegramMessageAIAnalysisDatabaseManager.insert(_ai_values(1, 100))
    media_dir = tmp_path / 'media' / '100'
    media_dir.mkdir(parents=True)
    media_file = media_dir / 'old.bin'
    media_file.write_bytes(b'old')
    media_id = TelegramMediaDatabaseManager.insert(
        {
            'group_id': 100,
            'telegram_id': 9,
            'file_name': media_file.name,
            'extension': '.bin',
            'height': None,
            'width': None,
            'date_time': old,
            'mime_type': 'application/octet-stream',
            'size_bytes': 3,
            'title': None,
            'name': None,
        }
    )
    await TelegramMaintenancePurgeOldData().run(
        _config(tmp_path),
        {'purge_old_data': True, 'limit_days': 5},
        {},
    )
    assert TelegramMessageAIAnalysisDatabaseManager.get_by_message(1, 100) is None
    assert database.scalars(select(TelegramMessageOrmEntity.id)).all() == [2]
    assert TelegramMediaDatabaseManager.get_by_id(media_id) is None
    assert not media_file.exists()


class FakeTelegramClient:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.started_phone = None
        self.session = SimpleNamespace(save=MagicMock())

    async def start(self, phone):
        self.started_phone = phone
        return self

    async def is_user_authorized(self):
        return True


@pytest.mark.asyncio
@pytest.mark.parametrize('connect', [True, False])
async def test_telegram_connection_creates_session_and_reuses_config(
    tmp_path, connect
):
    fake = FakeTelegramClient()
    with patch(
        'telos_x.modules.telegram_connection_manager.TelegramClient',
        return_value=fake,
    ):
        data = {'internals': {'panic': False}}
        args = {
            'connect': connect,
            'load_groups': not connect,
            'download_messages': False,
            'sent_report_telegram': False,
            'listen': False,
        }
        await TelegramConnector().run(_config(tmp_path), args, data)
    assert (tmp_path / 'session').is_dir()
    assert fake.started_phone == '+1000'
    assert data['telegram_client'] is fake


@pytest.mark.asyncio
async def test_saved_state_does_not_duplicate_telegram_credentials(database, tmp_path):
    config = _config(tmp_path)
    config.read_dict(
        {'MODULE_SaveStateFileHandler': {'file_name': 'state/{0}.json'}}
    )
    await SaveStateFileHandler().run(
        config,
        {},
        {
            'internals': {'panic': False},
            'telegram_connection': {
                'api_id': 12345,
                'api_hash': 'placeholder-hash',
                'target_phone_number': '+1000',
            },
        },
    )
    saved = json.loads(StateFileHandler.read_file_text('state/+1000.json'))
    assert saved['telegram_connection'] == {'target_phone_number': '+1000'}


def _notifier_section():
    config = configparser.ConfigParser()
    config.read_dict(
        {
            'NOTIFIER.TEST': {
                'prevent_duplication_for_minutes': '1',
                'only_rule_matches': 'false',
            }
        }
    )
    return config['NOTIFIER.TEST']


@pytest.mark.asyncio
async def test_slack_notifier_posts_with_timeout_and_checks_http(database):
    response = MagicMock()
    notifier = SlackNotifier()
    notifier.configure('https://example.invalid/slack', _notifier_section())
    with patch('telos_x.notifier.slack_notifier.requests.post', return_value=response) as post:
        await notifier.run(
            SimpleNamespace(raw_text='alert'),
            group_id=999,
            id=1,
            raw_text='alert',
            translation='alert',
        )
    assert post.call_args.kwargs['timeout'] == 10
    response.raise_for_status.assert_called_once()


@pytest.mark.asyncio
async def test_discord_notifier_executes_in_worker_thread():
    webhook = MagicMock()
    notifier = DiscordNotifier()
    notifier.configure('https://example.invalid/discord', _notifier_section())
    with patch('telos_x.notifier.discord_notifier.DiscordWebhook', return_value=webhook):
        await notifier.run(
            SimpleNamespace(
                id=1,
                raw_text='alert',
                message='alert',
                chat=SimpleNamespace(id=100, title='Group'),
                date=datetime.datetime.now(datetime.timezone.utc),
            ),
            group_id=100,
            id=1,
            severity='critical',
            risk_score=0.9,
            ai_result={},
        )
    webhook.add_embed.assert_called_once()
    webhook.execute.assert_called_once()


class ControlledNotifier:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = 0

    async def run(self, message, **kwargs):
        self.calls += 1
        if self.fail:
            raise RuntimeError('delivery failed')


@pytest.mark.asyncio
async def test_notifier_engine_continues_after_one_delivery_failure():
    failed = ControlledNotifier(fail=True)
    working = ControlledNotifier()
    engine = NotifierEngine()
    engine.notifiers = {
        'first': {'instance': failed},
        'second': {'instance': working},
    }
    await engine.run(SimpleNamespace(raw_text='message'))
    assert failed.calls == 1 and working.calls == 1


def test_notifier_engine_supports_no_configured_notifiers():
    engine = NotifierEngine()
    engine.configure(configparser.ConfigParser())
    assert engine.notifiers == {}
