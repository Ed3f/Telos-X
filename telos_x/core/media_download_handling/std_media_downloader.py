"""Standard Media Downloader."""
import os
from pathlib import Path
from typing import Dict, List

from telethon.tl.types import Message


class StandardMediaDownloader:
    """Standard Media Downloader."""

    @staticmethod
    async def download(message: Message, media_metadata: Dict, data_path: str) -> None:
        """Download the Media and Update MetadaInfo.

        :param message:
        :param media_metadata:
        :return:
        """
        if not media_metadata:
            return None

        # Download Media
        Path(data_path).mkdir(parents=True, exist_ok=True)
        target_path: str = os.path.join(data_path, StandardMediaDownloader.__sanitize_media_filename(media_metadata['file_name']))
        generated_path: str = await message.download_media(target_path)
        if not generated_path:
            raise OSError('Telegram media download returned no path')
        media_metadata['extension'] = os.path.splitext(generated_path)[1]

    @staticmethod
    def __sanitize_media_filename(filename: str) -> str:
        """Sanitize Media Filename."""
        sanit_charts: List[str] = [char for char in filename if not char.isalpha() and char != ' ' and not char.isalnum() and char != '.' and char != '-']
        h_result: str = filename

        for sanit_item in sanit_charts:
            h_result = h_result.replace(sanit_item, '_')

        return h_result
