"""Data Structure Handler."""

import os
from configparser import ConfigParser
from typing import Dict

from telos_x.core.base_module import BaseModule
from telos_x.core.dir_manager import DirectoryManagerUtils


class DataStructureHandler(BaseModule):
    """Create the Telos-X data directory structure."""

    async def can_activate(
        self,
        config: ConfigParser,
        args: Dict,
        data: Dict,
    ) -> bool:
        return config.has_option(
            "CONFIGURATION",
            "data_path",
        )

    async def run(
        self,
        config: ConfigParser,
        args: Dict,
        data: Dict,
    ) -> None:

        data_path = config.get(
            "CONFIGURATION",
            "data_path",
        )

        for folder in (
            "export",
            "download",
            "profile_pic",
            "media",
            "session",
        ):
            DirectoryManagerUtils.ensure_dir_struct(
                os.path.join(
                    data_path,
                    folder,
                )
            )