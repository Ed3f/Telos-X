"""Execution Configuration Loader."""

import logging
from configparser import ConfigParser, Error as ConfigError
from pathlib import Path
from typing import Dict

from telos_x.core.base_module import BaseModule

logger = logging.getLogger('TelegramExplorer')


class ExecutionConfigurationHandler(BaseModule):
    """Module That Handle the Input Arguments."""

    async def can_activate(self, config: ConfigParser, args: Dict, data: Dict) -> bool:
        """
        Abstract Method for Module Activation Function.

        :return:
        """
        return True

    async def run(self, config: ConfigParser, args: Dict, data: Dict) -> None:
        """Load Configuration for Execution."""
        logger.info('[*] Loading Execution Configurations:')

        configured_path = args.get('config')
        if not configured_path:
            logger.fatal('[?] CONFIGURATION FILE IS REQUIRED')
            data['internals']['panic'] = True
            return

        config_path = Path(configured_path).expanduser().resolve()
        if not config_path.is_file():
            logger.fatal(f'[?] CONFIGURATION FILE NOT FOUND AT \"{args["config"]}\"')
            data['internals']['panic'] = True
            return

        try:
            config.read(config_path)
        except ConfigError as exc:
            logger.fatal('[?] INVALID CONFIGURATION FILE: %s', exc)
            data['internals']['panic'] = True
            return

        if not config.has_section('CONFIGURATION'):
            logger.fatal('[?] MISSING REQUIRED [CONFIGURATION] SECTION')
            data['internals']['panic'] = True
            return

        for option in ('data_path', 'phone_number'):
            if not config.get('CONFIGURATION', option, fallback='').strip():
                logger.fatal('[?] MISSING REQUIRED CONFIGURATION OPTION: %s', option)
                data['internals']['panic'] = True
                return

        for option in ('data_path', 'groups_file'):
            value = config.get('CONFIGURATION', option, fallback='').strip()
            if not value:
                continue
            path = Path(value).expanduser()
            if not path.is_absolute():
                path = config_path.parent / path
            config['CONFIGURATION'][option] = str(path.resolve())

        report_folder = args.get('report_folder')
        if report_folder:
            report_path = Path(report_folder).expanduser()
            if not report_path.is_absolute():
                report_path = Path(config['CONFIGURATION']['data_path']) / report_path
            args['report_folder'] = str(report_path.resolve())

        if args.get('limit_days') is not None and int(args['limit_days']) < 0:
            logger.fatal('[?] --limit_days must be zero or greater')
            data['internals']['panic'] = True
