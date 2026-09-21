"""Photo Media Downloader."""
import os
from pathlib import Path
from typing import Dict

from telethon.tl.types import Message


class PhotoMediaDownloader:
    """Photo Media Downloader."""

    @staticmethod
    async def download(message: Message, media_metadata: Dict, data_path: str) -> None:
        """Download the Media and Update MetadaInfo.

        :param message:
        :param media_metadata:
        :return:
        """
        # Download Media
        Path(data_path).mkdir(parents=True, exist_ok=True)
        generated_path = await message.download_media(
            os.path.join(data_path, media_metadata['file_name'])
        )
        if not generated_path:
            raise OSError('Telegram photo download returned no path')
