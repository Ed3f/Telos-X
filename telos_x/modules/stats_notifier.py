"""Periodic Telos-X operational status notifications."""

import asyncio
import logging
import re
import threading
from configparser import ConfigParser
from datetime import datetime, timedelta
from typing import Dict, List, Optional, cast

from telethon import TelegramClient

from telos_x.core.base_module import BaseModule
from telos_x.database.telegram_group_database import TelegramGroupDatabaseManager
from telos_x.notifier.notifier_engine import NotifierEngine
from telos_x.utils import Os_stat, active_groups


logger = logging.getLogger('TelegramExplorer')


class Job(threading.Thread):
    """Run one callback daily at a configured local time."""

    def __init__(self, hour: int, minute: int, execute) -> None:
        super().__init__(daemon=True)
        self.stopped = threading.Event()
        self.hour = hour
        self.minute = minute
        self.execute = execute

    def _compute_interval(self) -> float:
        now = datetime.now()
        target = now.replace(
            hour=self.hour,
            minute=self.minute,
            second=0,
            microsecond=0,
        )
        if now >= target:
            target += timedelta(days=1)
        return (target - now).total_seconds()

    def run(self) -> None:
        while not self.stopped.wait(self._compute_interval()):
            try:
                self.execute()
            except Exception:
                logger.exception('Unable to produce the scheduled Telos-X status')


class StatsNotifier(BaseModule):
    """Produce disk and monitored-group status through configured notifiers."""

    def __init__(self) -> None:
        self.jobs: List[Job] = []
        self._config: Optional[ConfigParser] = None
        self._client: Optional[TelegramClient] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._notifier = NotifierEngine()
        self._target_notifiers: Optional[List[str]] = None

    async def can_activate(
        self,
        config: ConfigParser,
        args: Dict,
        data: Dict,
    ) -> bool:
        """Keep the existing listener-based activation policy."""
        del data
        return cast(
            bool,
            args.get('listen', False)
            and config.getboolean('STATS_NOTIFIER', 'enabled', fallback=False),
        )

    async def run(self, config: ConfigParser, args: Dict, data: Dict) -> None:
        """Configure one daily operational status job."""
        del args
        self._config = config
        self._client = data['telegram_client']
        self._loop = asyncio.get_running_loop()
        self._notifier.configure(config)

        notifier_value = config.get(
            'STATS_NOTIFIER',
            'notifiers',
            fallback='',
        )
        configured_targets = [
            value
            for value in re.split(r'[\s,]+', notifier_value.strip())
            if value
        ]
        self._target_notifiers = configured_targets or None

        hour = config.getint('STATS_NOTIFIER', 'hour', fallback=9)
        minute = config.getint('STATS_NOTIFIER', 'minute', fallback=0)
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            logger.error('Invalid STATS_NOTIFIER schedule %02d:%02d', hour, minute)
            return
        status_job = Job(hour, minute, self._dispatch_scheduled_status)
        self.jobs.append(status_job)
        status_job.start()

    def _dispatch_scheduled_status(self) -> None:
        """Dispatch the async status task back to the Telethon event loop."""
        if self._loop is None or self._loop.is_closed():
            logger.warning('Cannot send Telos-X status: event loop is unavailable')
            return
        future = asyncio.run_coroutine_threadsafe(
            self._notify_status(),
            self._loop,
        )
        future.result(timeout=120)

    async def _notify_status(self) -> None:
        if self._config is None or self._client is None:
            return

        data_path = self._config['CONFIGURATION']['data_path']
        phone_number = self._config['CONFIGURATION']['phone_number']
        system_stats = await asyncio.to_thread(
            Os_stat.get_system_stats,
            data_path,
        )
        monitored_groups = TelegramGroupDatabaseManager.get_all_by_phone_number(
            phone_number
        )
        group_stats = await active_groups.get_active_groups(
            self._client,
            [group.id for group in monitored_groups],
        )
        await self._notifier.send_text(
            self.format_status(system_stats, group_stats),
            notifiers=self._target_notifiers,
        )

    @staticmethod
    def format_status(system_stats: Dict, group_stats: Dict) -> str:
        """Render a compact status payload shared by Slack and Discord."""
        disk = system_stats['disk']
        return (
            'Telos-X Status\n\n'
            'Disk:\n'
            f"Total: {disk['total_gb']:.2f} GB\n"
            f"Used: {disk['used_gb']:.2f} GB\n"
            f"Free: {disk['free_gb']:.2f} GB\n"
            f"Usage: {disk['percent_used']:.2f}%\n\n"
            'Groups:\n'
            f"Monitored: {group_stats['total']}\n"
            f"UP: {group_stats['up_count']}/{group_stats['total']}\n"
            f"DOWN: {group_stats['down_count']}"
        )
