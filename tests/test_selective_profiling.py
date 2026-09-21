"""Tests for configurable selective Telegram user profiling."""

import tempfile
import unittest
from configparser import ConfigParser
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from telos_x.modules.telegram_groups_scrapper import TelegramGroupScrapper


class _FakeProfilingClient:
    def __init__(self) -> None:
        self.full_user_requests = []

    async def __call__(self, request):
        self.full_user_requests.append(request)
        return SimpleNamespace(
            full_user=SimpleNamespace(
                about='extended',
                profile_photo=None,
            )
        )

    async def get_profile_photos(self, _user_id):
        return []


class SelectiveProfilingTests(unittest.IsolatedAsyncioTestCase):
    """Verify disabled, allowlist, and profile-all behavior."""

    def setUp(self) -> None:
        self.scraper = TelegramGroupScrapper()

    @staticmethod
    def _config(**profiling_values) -> ConfigParser:
        values = {
            'enabled': 'true',
            'profile_all_users': 'false',
            'target_usernames': '',
            'target_first_names': '',
        }
        values.update(profiling_values)
        config = ConfigParser()
        config.read_dict(
            {
                'CONFIGURATION': {'data_path': '.'},
                'PROFILING': values,
            }
        )
        return config

    @staticmethod
    def _members() -> list[dict]:
        return [
            {'id': 1, 'username': '@Target_User', 'first_name': 'One'},
            {'id': 2, 'username': 'other', 'first_name': 'Exodius'},
            {'id': 3, 'username': 'third', 'first_name': 'Three'},
        ]

    async def _run_profiling(self, config: ConfigParser) -> int:
        client = _FakeProfilingClient()
        with tempfile.TemporaryDirectory() as data_path, patch(
            'telos_x.modules.telegram_groups_scrapper.'
            'TelegramUserDatabaseManager.insert_or_update'
        ):
            await self.scraper._profile_selected_users(
                client=client,
                members=self._members(),
                data_path=data_path,
                config=config,
            )
        return len(client.full_user_requests)

    async def test_disabled_profiles_nobody(self) -> None:
        config = self._config(enabled='false', profile_all_users='true')
        self.assertEqual(0, await self._run_profiling(config))

    async def test_allowlist_is_case_insensitive_and_accepts_at_username(self) -> None:
        config = self._config(
            target_usernames='target_user,\n example_user',
            target_first_names='exodius',
        )
        self.assertEqual(2, await self._run_profiling(config))

    async def test_profile_all_users_profiles_everybody(self) -> None:
        config = self._config(profile_all_users='true')
        self.assertEqual(3, await self._run_profiling(config))

    def test_groups_csv_uses_configured_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            groups_file = Path(directory) / 'groups.csv'
            groups_file.write_text(
                'telegram_group\nhttps://t.me/example_group\n',
                encoding='utf-8',
            )
            config = self._config()
            config['CONFIGURATION']['groups_file'] = str(groups_file)
            self.assertEqual(
                ['https://t.me/example_group'],
                self.scraper._load_group_links(config),
            )

    def test_missing_groups_csv_returns_empty_list(self) -> None:
        config = self._config()
        config['CONFIGURATION']['groups_file'] = 'missing/groups.csv'
        self.assertEqual([], self.scraper._load_group_links(config))


if __name__ == '__main__':
    unittest.main()
