"""Temporary Files Manager."""

import logging
from configparser import ConfigParser
from typing import Dict

from TELOSX.core.base_module import BaseModule
from TELOSX.core.temp_file import TempFileHandler

logger = logging.getLogger('TelegramExplorer')


class TempFileManager(BaseModule):
    """Temporary File Manager."""

    async def can_activate(self, config: ConfigParser, args: Dict, data: Dict) -> bool:
        """
        Abstract Method for Module Activation Function.

        :return:
        """
        return True

    async def run(self, config: ConfigParser, args: Dict, data: Dict) -> None:
        """Execute Module."""
        if args['purge_temp_files']:
            TempFileHandler.purge()

        else:
            TempFileHandler.remove_expired_entries()
