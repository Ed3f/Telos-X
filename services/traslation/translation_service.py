import time
import logging
from typing import Optional

from telethon.errors import FloodWaitError

from .schemas import TranslationResult
from .telegram_provider import TelegramTranslationProvider
from .local_provider import CTranslate2LocalTranslationProvider

logger = logging.getLogger("TelegramExplorer")


class TranslationService:
    """
    Service unico di orchestrazione della traduzione.

    Politica:
    - prova Telegram
    - se FloodWait, mette Telegram in cooldown
    - usa fallback locale NLLB + CTranslate2 su GPU
    """

    def __init__(
        self,
        telegram_provider: Optional[TelegramTranslationProvider] = None,
        local_provider: Optional[CTranslate2LocalTranslationProvider] = None,
    ):
        self.telegram_provider = telegram_provider or TelegramTranslationProvider()

        self.local_provider = local_provider or CTranslate2LocalTranslationProvider(
            model_path="models/nllb-200-distilled-600M-ct2",
            hf_tokenizer_name="facebook/nllb-200-distilled-600M",
            device="cuda",
            compute_type="float16",
            inter_threads=1,
            intra_threads=0,
            beam_size=4,
            max_decoding_length=256,
        )

        self.telegram_blocked_until: float = 0.0

    def _telegram_available(self) -> bool:
        return time.time() >= self.telegram_blocked_until

    def _block_telegram(self, seconds: int) -> None:
        self.telegram_blocked_until = time.time() + max(seconds, 1)
        logger.warning(
            "[TRANSLATION] Telegram provider blocked for %s seconds due to flood wait",
            seconds,
        )

    async def translate(
        self,
        text: str,
        source_lang: Optional[str] = None,
        target_lang: str = "eng_Latn",
        **kwargs
    ) -> TranslationResult:
        if not text or not text.strip():
            return TranslationResult(
                original_text=text or "",
                translated_text=text or "",
                provider="none",
                used_fallback=False,
                success=False,
                source_lang=source_lang,
                target_lang=target_lang,
                error="empty_text",
            )

        if self._telegram_available():
            try:
                result = await self.telegram_provider.translate(
                    text=text,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    **kwargs
                )
                if result.success:
                    return result

            except FloodWaitError as exc:
                self._block_telegram(exc.seconds + 1)
                logger.warning(
                    "[TRANSLATION] FloodWaitError detected. Switching to local GPU provider."
                )

        fallback_result = await self.local_provider.translate(
            text=text,
            source_lang=source_lang,
            target_lang=target_lang,
            **kwargs
        )
        return fallback_result