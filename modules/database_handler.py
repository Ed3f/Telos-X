"""Database Handler."""

import logging
import os
from configparser import ConfigParser
from typing import Dict

from TELOSX.core.base_module import BaseModule
from TELOSX.core.temp_file import TempFileHandler
from TELOSX.database.db_initializer import DbInitializer

logger = logging.getLogger('TelegramExplorer')


class DatabaseHandler(BaseModule):
    """Module That Handle the Internal DB."""

    async def can_activate(self, config: ConfigParser, args: Dict, data: Dict) -> bool:
        """
        Abstract Method for Module Activation Function.

        :return:
        """
        return True

    async def run(self, config: ConfigParser, args: Dict, data: Dict) -> None:
        """Execute."""
        if not os.path.exists(config['CONFIGURATION']['data_path']):
            os.mkdir(config['CONFIGURATION']['data_path'])

        # Initialize DB
        DbInitializer.init(config['CONFIGURATION']['data_path'])

        # Expire Temp Files
        TempFileHandler.remove_expired_entries()
