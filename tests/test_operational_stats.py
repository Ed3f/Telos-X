"""Tests for active group and system status utilities."""

import tempfile
import unittest
import configparser
import asyncio
from unittest.mock import patch
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from telos_x.modules.stats_notifier import StatsNotifier
from telos_x.schedule import scheduled_message
from telos_x.utils import Os_stat, active_groups


class _FakeTelegramClient:
    async def get_entity(self, group_id: int):
        if group_id == 2:
            raise ValueError('unreachable')
        return SimpleNamespace(title=f'Group {group_id}', username=None)


class OperationalStatsTests(unittest.IsolatedAsyncioTestCase):
    """Verify status collection and rendering without external notifications."""

    async def test_active_groups_reports_up_and_down(self) -> None:
        result = await active_groups.get_active_groups(
            _FakeTelegramClient(),
            [1, 2],
        )
        self.assertEqual(2, result['total'])
        self.assertEqual(1, result['up_count'])
        self.assertEqual(1, result['down_count'])

    def test_disk_stats_use_configurable_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            stats = Os_stat.get_system_stats(
                str(Path(directory) / 'future-data-directory')
            )
        self.assertIn('total_gb', stats['disk'])
        self.assertIn('used_gb', stats['disk'])
        self.assertIn('free_gb', stats['disk'])
        self.assertIn('percent_used', stats['disk'])

    def test_status_report_contains_disk_and_group_summary(self) -> None:
        report = StatsNotifier.format_status(
            {
                'disk': {
                    'total_gb': 100.0,
                    'used_gb': 40.0,
                    'free_gb': 60.0,
                    'percent_used': 40.0,
                }
            },
            {
                'total': 20,
                'up_count': 18,
                'down_count': 2,
            },
        )
        self.assertIn('Telos-X Status', report)
        self.assertIn('UP: 18/20', report)
        self.assertIn('DOWN: 2', report)

    def test_legacy_schedule_helper_uses_today_when_time_is_ahead(self) -> None:
        with patch('telos_x.schedule.datetime') as mocked_datetime:
            mocked_datetime.now.return_value = datetime(2026, 8, 22, 8, 0)
            self.assertEqual(3600, scheduled_message(9, 0))

    def test_stats_notifier_is_opt_in_when_section_is_missing(self) -> None:
        enabled = asyncio.run(
            StatsNotifier().can_activate(
                configparser.ConfigParser(),
                {'listen': True},
                {},
            )
        )
        self.assertFalse(enabled)


if __name__ == '__main__':
    unittest.main()
