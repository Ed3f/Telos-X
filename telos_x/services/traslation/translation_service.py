"""Translation service orchestration."""

import logging
import time
from typing import Optional

from telethon.errors import FloodWaitError

from .local_provider import CTranslate2LocalTranslationProvider
from .schemas import TranslationResult
from .telegram_provider import TelegramTranslationProvider


logger = logging.getLogger("TelegramExplorer")


class TranslationService:
    """
    Orchestrates translation providers.

    Translation policy:

    1. Telegram Translation is the preferred provider.
    2. If Telegram returns a FloodWaitError:
       - Telegram is temporarily placed in cooldown;
       - the current message is immediately sent to the local provider.
    3. While Telegram is in cooldown:
       - subsequent messages are sent directly to the local provider.
    4. When the cooldown expires:
       - Telegram is tried again automatically.
    5. If the local provider cannot be initialized:
       - Telegram remains available;
       - the rest of the Telos-X pipeline can continue even when
         translation is temporarily unavailable.

    This prevents a Telegram FloodWait from blocking the entire
    scraping/listening pipeline.
    """

    def __init__(
        self,
        telegram_provider: Optional[
            TelegramTranslationProvider
        ] = None,
        local_provider: Optional[
            CTranslate2LocalTranslationProvider
        ] = None,
        model_path: str = "models/nllb-200-distilled-600M-ct2",
        tokenizer_name: str = "facebook/nllb-200-distilled-600M",
        device: str = "cuda",
        compute_type: str = "float16",
        inter_threads: int = 1,
        intra_threads: int = 0,
        beam_size: int = 4,
        max_decoding_length: int = 256,
    ) -> None:
        """
        Initialize the translation service.

        Args:
            telegram_provider:
                Optional pre-built Telegram translation provider.

            local_provider:
                Optional pre-built local CTranslate2 provider.

            model_path:
                Path to the NLLB model converted to CTranslate2 format.

            tokenizer_name:
                Hugging Face tokenizer associated with the NLLB model.

            device:
                CTranslate2 execution device, typically ``cuda`` or ``cpu``.

            compute_type:
                CTranslate2 computation type, e.g. ``float16``.

            inter_threads:
                Number of CTranslate2 translation workers.

            intra_threads:
                Number of CPU threads used by each worker.

            beam_size:
                Beam size used by NLLB.

            max_decoding_length:
                Maximum number of generated tokens.
        """

        # Telegram must remain independent from the local provider.
        self.telegram_provider = (
            telegram_provider
            or TelegramTranslationProvider()
        )

        self.local_provider = local_provider

        # The local provider is optional.
        #
        # If NLLB, CUDA, CTranslate2 or the model files are unavailable,
        # TranslationService must still be created so that Telegram
        # Translation remains operational.
        if self.local_provider is None:
            try:
                self.local_provider = (
                    CTranslate2LocalTranslationProvider(
                        model_path=model_path,
                        hf_tokenizer_name=tokenizer_name,
                        device=device,
                        compute_type=compute_type,
                        inter_threads=inter_threads,
                        intra_threads=intra_threads,
                        beam_size=beam_size,
                        max_decoding_length=max_decoding_length,
                    )
                )

                logger.info(
                    "[TRANSLATION] Local CTranslate2 provider initialized "
                    "successfully."
                )

            except Exception as exc:
                self.local_provider = None

                logger.warning(
                    "[TRANSLATION] Local CTranslate2 provider unavailable. "
                    "Telegram Translation will remain available: %s",
                    exc,
                )

        # Monotonic timestamp until which Telegram must not be retried.
        self.telegram_blocked_until: float = 0.0

    def _telegram_available(self) -> bool:
        """
        Return True when Telegram Translation can currently be used.

        ``time.monotonic`` is intentionally used instead of ``time.time``
        because cooldown duration must not be affected by system-clock
        changes.
        """
        return (
            time.monotonic()
            >= self.telegram_blocked_until
        )

    def _block_telegram(
        self,
        seconds: int,
    ) -> None:
        """
        Temporarily disable Telegram Translation after a FloodWait.

        The rest of the pipeline is not suspended: translations are
        redirected to the local provider while the cooldown is active.
        """
        cooldown_seconds = max(
            int(seconds),
            1,
        )

        self.telegram_blocked_until = (
            time.monotonic()
            + cooldown_seconds
        )

        logger.warning(
            "[TRANSLATION] Telegram provider blocked for %s seconds "
            "due to FloodWait.",
            cooldown_seconds,
        )

    def _providers_unavailable_result(
        self,
        *,
        text: str,
        source_lang: Optional[str],
        target_lang: str,
        error: str = "translation_providers_unavailable",
    ) -> TranslationResult:
        """
        Return a safe translation failure while preserving the raw text.

        The caller can therefore continue the CTI pipeline using the
        original message instead of crashing or dropping it.
        """
        return TranslationResult(
            original_text=text,
            translated_text=text,
            provider="none",
            used_fallback=False,
            success=False,
            source_lang=source_lang,
            target_lang=target_lang,
            error=error,
        )

    async def _translate_with_local(
        self,
        text: str,
        source_lang: Optional[str],
        target_lang: str,
        **kwargs,
    ) -> TranslationResult:
        """
        Translate using the local CTranslate2 provider when available.
        """
        if self.local_provider is None:
            logger.warning(
                "[TRANSLATION] Local provider requested but unavailable."
            )

            return self._providers_unavailable_result(
                text=text,
                source_lang=source_lang,
                target_lang=target_lang,
                error="local_translation_provider_unavailable",
            )

        try:
            result = await self.local_provider.translate(
                text=text,
                source_lang=source_lang,
                target_lang=target_lang,
                **kwargs,
            )

            return result

        except Exception as exc:
            logger.exception(
                "[TRANSLATION] Unexpected error in local provider."
            )

            return self._providers_unavailable_result(
                text=text,
                source_lang=source_lang,
                target_lang=target_lang,
                error=(
                    "local_translation_error:"
                    f"{type(exc).__name__}: {exc}"
                ),
            )

    async def translate(
        self,
        text: str,
        source_lang: Optional[str] = None,
        target_lang: str = "eng_Latn",
        **kwargs,
    ) -> TranslationResult:
        """
        Translate a message according to the Telos-X provider policy.

        Normal flow:

            Telegram
                |
                +-- success --------------------> return translation
                |
                +-- FloodWait
                        |
                        +--> set cooldown
                        |
                        +--> local provider

        During cooldown:

            local provider directly

        After cooldown:

            Telegram is automatically tried again.
        """

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

        # ---------------------------------------------------------
        # 1. TELEGRAM PROVIDER
        # ---------------------------------------------------------

        if self._telegram_available():
            try:
                telegram_result = (
                    await self.telegram_provider.translate(
                        text=text,
                        source_lang=source_lang,
                        target_lang=target_lang,
                        **kwargs,
                    )
                )

                if telegram_result.success:
                    return telegram_result

                # Telegram did not raise FloodWait but failed for another
                # reason (e.g. missing client, API error, etc.).
                #
                # Do not block Telegram globally for these failures:
                # simply use the local fallback for this message.
                logger.warning(
                    "[TRANSLATION] Telegram provider failed: %s. "
                    "Trying local provider.",
                    telegram_result.error,
                )

            except FloodWaitError as exc:
                # Telegram communicates the required waiting time through
                # exc.seconds.
                cooldown_seconds = (
                    int(exc.seconds)
                    + 1
                )

                self._block_telegram(
                    cooldown_seconds
                )

                logger.warning(
                    "[TRANSLATION] FloodWaitError detected. "
                    "Switching immediately to local translation."
                )

            except Exception:
                # Defensive protection.
                #
                # The Telegram provider currently converts ordinary errors
                # to TranslationResult, but TranslationService should still
                # protect the pipeline if the provider implementation
                # changes in the future.
                logger.exception(
                    "[TRANSLATION] Unexpected Telegram provider error. "
                    "Trying local provider."
                )

        else:
            remaining = max(
                self.telegram_blocked_until
                - time.monotonic(),
                0.0,
            )

            logger.debug(
                "[TRANSLATION] Telegram provider still in cooldown "
                "(%.1f seconds remaining). Using local provider.",
                remaining,
            )

        # ---------------------------------------------------------
        # 2. LOCAL FALLBACK
        # ---------------------------------------------------------

        local_result = await self._translate_with_local(
            text=text,
            source_lang=source_lang,
            target_lang=target_lang,
            **kwargs,
        )

        return local_result
