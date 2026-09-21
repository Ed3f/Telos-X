"""Package, CLI, path, and configuration smoke tests."""

import asyncio
import configparser
import subprocess
import sys
from pathlib import Path

import pytest

import telos_x
import telos_x.runner
from telos_x.modules.execution_configuration_handler import ExecutionConfigurationHandler
from telos_x.modules.input_args_handler import InputArgsHandler


def test_package_and_runner_import():
    assert telos_x.__version__ == '0.1.0'
    assert telos_x.runner.TelegramMonitorRunner


def test_cli_help_from_repository_root():
    result = subprocess.run(
        [sys.executable, '-m', 'telos_x', '--help'],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert 'load_groups' in result.stdout
    assert 'messages_analysys' not in result.stdout


@pytest.mark.asyncio
async def test_config_paths_resolve_relative_to_config(tmp_path):
    config_file = tmp_path / 'settings.ini'
    config_file.write_text(
        '[CONFIGURATION]\n'
        'phone_number=+1000\n'
        'data_path=runtime\n'
        'groups_file=input/groups.csv\n',
        encoding='utf-8',
    )
    config = configparser.ConfigParser()
    data = {'internals': {'panic': False}}
    args = {'config': str(config_file), 'report_folder': 'reports'}
    await ExecutionConfigurationHandler().run(config, args, data)
    assert not data['internals']['panic']
    assert Path(config['CONFIGURATION']['data_path']) == tmp_path / 'runtime'
    assert Path(config['CONFIGURATION']['groups_file']) == tmp_path / 'input/groups.csv'
    assert Path(args['report_folder']) == tmp_path / 'runtime/reports'


@pytest.mark.asyncio
async def test_missing_required_config_is_clear(tmp_path, caplog):
    config_file = tmp_path / 'bad.ini'
    config_file.write_text('[CONFIGURATION]\ndata_path=data\n', encoding='utf-8')
    config = configparser.ConfigParser()
    data = {'internals': {'panic': False}}
    await ExecutionConfigurationHandler().run(
        config,
        {'config': str(config_file)},
        data,
    )
    assert data['internals']['panic']
    assert 'phone_number' in caplog.text


@pytest.mark.parametrize(
    'action,extra',
    [
        ('connect', []),
        ('load_groups', []),
        ('download_messages', []),
        ('listen', []),
        ('list_groups', []),
        ('report', []),
        ('graph', []),
        ('export_text', []),
        ('export_file', []),
        ('sent_report_telegram', ['--destination_username', 'test']),
        ('stats', []),
        ('purge_old_data', []),
        ('purge_temp_files', []),
    ],
)
def test_every_cli_action_parses(monkeypatch, action, extra):
    monkeypatch.setattr(
        sys,
        'argv',
        ['telos-x', action, '--config', 'settings.ini', *extra],
    )
    args = {}
    asyncio.run(
        InputArgsHandler().run(
            configparser.ConfigParser(),
            args,
            {'internals': {'panic': False}},
        )
    )
    assert args[action]


def test_cli_applies_declared_numeric_types(monkeypatch):
    monkeypatch.setattr(
        sys,
        'argv',
        ['telos-x', 'stats', '--config', 'settings.ini', '--limit_days', '5'],
    )
    args = {}
    asyncio.run(
        InputArgsHandler().run(
            configparser.ConfigParser(),
            args,
            {'internals': {'panic': False}},
        )
    )
    assert args['limit_days'] == 5
