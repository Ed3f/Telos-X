"""Telegram Checker Handler."""
import logging
import platform
from configparser import ConfigParser
from pathlib import Path
from typing import Dict, cast

from telethon import TelegramClient

from telos_x.core.base_module import BaseModule

logger = logging.getLogger('TelegramExplorer')


class TelegramConnector(BaseModule):
    """Telegram Connection Manager - Connect."""

    async def can_activate(self, config: ConfigParser, args: Dict, data: Dict) -> bool:
        """
        Abstract Method for Module Activation Function.

        :return:
        """
        return cast(bool, args['connect'] or args['load_groups'] or args['download_messages'] or args['sent_report_telegram'] or args['listen'])

    async def run(self, config: ConfigParser, args: Dict, data: Dict) -> None:
        """Execute Module."""
        if not await self.can_activate(config, args, data):
            return

        session_dir = Path(config['CONFIGURATION']['data_path']) / 'session'
        session_dir.mkdir(parents=True, exist_ok=True)

        saved = data.get('telegram_connection', {})
        api_id_value = config.get(
            'CONFIGURATION', 'api_id', fallback=str(saved.get('api_id', ''))
        ).strip()
        api_hash = config.get(
            'CONFIGURATION', 'api_hash', fallback=str(saved.get('api_hash', ''))
        ).strip()
        phone_number = config.get(
            'CONFIGURATION',
            'phone_number',
            fallback=str(saved.get('target_phone_number', '')),
        ).strip()
        if not api_id_value or not api_hash or not phone_number:
            logger.error(
                'Telegram requires CONFIGURATION.api_id, api_hash, and '
                'phone_number (values are not logged).'
            )
            data['internals']['panic'] = True
            return
        try:
            api_id = int(api_id_value)
        except ValueError:
            logger.error('CONFIGURATION.api_id must be an integer.')
            data['internals']['panic'] = True
            return

        device_model: str = self.__get_device_model_name(config=config)

        # Check Activation Command
        if args['connect']:  # New Connection
            logger.info('\t\tAuthorizing on Telegram...')

            # Connect
            client = TelegramClient(
                str(session_dir / phone_number),
                api_id,
                api_hash,
                catch_up=True,
                device_model=device_model
                )
            await client.start(phone=phone_number)
            client.session.save()

            # Save Data into State File
            data['telegram_connection'] = {
                'target_phone_number': phone_number
                }

        else:  # Reuse Previous Connection
            client = TelegramClient(
                str(session_dir / phone_number),
                api_id,
                api_hash,
                catch_up=True,
                device_model=device_model
                )
            await client.start(phone=phone_number)

        data['telegram_client'] = client
        logger.info('\t\tUser Authorized on Telegram: %s', await client.is_user_authorized())

    def __get_device_model_name(self, config: ConfigParser) -> str:
        """
        Compute Device Model Name for Telegram API.

        :return:
        """
        # Get Value from Configuration File
        device_model_name: str = config['CONFIGURATION']['device_model'] if 'device_model' in config['CONFIGURATION'] else 'telos_x'

        # Check for Automatic Configuration
        if device_model_name == 'AUTO':
            try:
                return platform.uname().machine

            except Exception:  # noqa: B902
                return 'telos_x'

        return device_model_name


class TelegramDisconnector(BaseModule):
    """Telegram Connection Manager - Connect."""

    async def can_activate(self, config: ConfigParser, args: Dict, data: Dict) -> bool:
        """
        Abstract Method for Module Activation Function.

        :return:
        """
        return 'telegram_client' in data and data['telegram_client']

    async def run(self, config: ConfigParser, args: Dict, data: Dict) -> None:
        """Execute Module."""
        if not await self.can_activate(config, args, data):
            return

        await data['telegram_client'].disconnect()
        del data['telegram_client']
