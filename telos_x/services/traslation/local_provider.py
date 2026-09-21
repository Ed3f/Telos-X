"""Local translation provider based on CTranslate2 and NLLB."""

import asyncio
import threading
from pathlib import Path
from typing import Dict, Optional

from langdetect import LangDetectException, detect

try:
    import ctranslate2
except ImportError:  # Optional local-translation extra.
    ctranslate2 = None  # type: ignore[assignment]

try:
    import transformers
except ImportError:  # Optional BERT/local-translation extra.
    transformers = None  # type: ignore[assignment]

from .base_provider import BaseTranslationProvider
from .schemas import TranslationResult


class CTranslate2LocalTranslationProvider(BaseTranslationProvider):
    """
    Local multilingual translation provider based on CTranslate2 + NLLB.

    The provider:
    - uses a single multilingual NLLB model;
    - detects the source language when it is not explicitly provided;
    - accepts both ISO language codes (e.g. ``ru``) and NLLB/FLORES
      language codes (e.g. ``rus_Cyrl``);
    - translates to English (``eng_Latn``) by default;
    - runs blocking CTranslate2 inference outside the asyncio event loop.
    """

    provider_name = "local_ctranslate2_nllb"

    # ISO 639-style codes returned by langdetect -> NLLB/FLORES codes.
    LANG_MAP: Dict[str, str] = {
        "ar": "arb_Arab",
        "ru": "rus_Cyrl",
        "uk": "ukr_Cyrl",
        "it": "ita_Latn",
        "en": "eng_Latn",
        "fr": "fra_Latn",
        "es": "spa_Latn",
        "de": "deu_Latn",
        "tr": "tur_Latn",
        "fa": "pes_Arab",
        "pt": "por_Latn",
    }

    def __init__(
        self,
        model_path: str,
        hf_tokenizer_name: str = "facebook/nllb-200-distilled-600M",
        device: str = "cuda",
        compute_type: str = "float16",
        inter_threads: int = 1,
        intra_threads: int = 0,
        beam_size: int = 4,
        max_decoding_length: int = 256,
    ) -> None:
        """
        Initialize the local NLLB translation provider.

        Args:
            model_path:
                Path to the NLLB model converted to CTranslate2 format.
            hf_tokenizer_name:
                Hugging Face tokenizer used by the original NLLB model.
            device:
                CTranslate2 execution device (``cuda`` or ``cpu``).
            compute_type:
                CTranslate2 compute type, e.g. ``float16``.
            inter_threads:
                Number of parallel translation workers.
            intra_threads:
                Number of CPU threads used by each worker.
            beam_size:
                Beam size used during translation.
            max_decoding_length:
                Maximum number of generated target tokens.
        """
        model_dir = Path(model_path).expanduser()

        if ctranslate2 is None or transformers is None:
            raise RuntimeError(
                "Local translation requires the 'local-translation' extra"
            )

        if not model_dir.is_dir():
            raise FileNotFoundError(
                f"CTranslate2 model directory not found: {model_dir}"
            )

        self.model_path = str(model_dir)
        self.hf_tokenizer_name = hf_tokenizer_name
        self.device = device
        self.compute_type = compute_type
        self.inter_threads = inter_threads
        self.intra_threads = intra_threads
        self.beam_size = beam_size
        self.max_decoding_length = max_decoding_length

        # NLLB's tokenizer has mutable source-language state.
        # The lock prevents concurrent translations from changing src_lang
        # while another message is being tokenized.
        self._translation_lock = threading.Lock()

        self.tokenizer = transformers.AutoTokenizer.from_pretrained(
            self.hf_tokenizer_name
        )

        self.translator = ctranslate2.Translator(
            self.model_path,
            device=self.device,
            compute_type=self.compute_type,
            inter_threads=self.inter_threads,
            intra_threads=self.intra_threads,
        )

    def _detect_language(self, text: str) -> Optional[str]:
        """
        Detect the source language and return its NLLB/FLORES code.

        Returns:
            NLLB language code when supported, otherwise ``None``.
        """
        try:
            detected_lang = detect(text)

            return self.LANG_MAP.get(
                detected_lang.lower()
            )

        except LangDetectException:
            return None

        except Exception:
            return None

    def _resolve_source_language(
        self,
        text: str,
        source_lang: Optional[str],
    ) -> Optional[str]:
        """
        Resolve the requested source language to an NLLB/FLORES code.

        Both simple ISO codes and native NLLB codes are accepted.

        Examples:
            ``ru`` -> ``rus_Cyrl``
            ``rus_Cyrl`` -> ``rus_Cyrl``
        """
        if source_lang:
            normalized_lang = source_lang.strip()

            # Already an NLLB/FLORES language code.
            if normalized_lang in self.LANG_MAP.values():
                return normalized_lang

            # ISO language code.
            iso_lang = normalized_lang.lower()

            if iso_lang in self.LANG_MAP:
                return self.LANG_MAP[iso_lang]

            return None

        return self._detect_language(text)

    def supports_language(
        self,
        source_lang: Optional[str],
        target_lang: str = "eng_Latn",
    ) -> bool:
        """
        Check whether source and target languages are supported.
        """
        if source_lang is None:
            return False

        supported_languages = set(
            self.LANG_MAP.values()
        )

        return (
            source_lang in supported_languages
            and target_lang in supported_languages
        )

    def _failure_result(
        self,
        *,
        text: str,
        source_lang: Optional[str],
        target_lang: str,
        error: str,
    ) -> TranslationResult:
        """
        Build a failed translation result while preserving the input text.
        """
        return TranslationResult(
            original_text=text,
            translated_text=text,
            provider=self.provider_name,
            used_fallback=True,
            success=False,
            source_lang=source_lang,
            target_lang=target_lang,
            error=error,
        )

    def _translate_sync(
        self,
        text: str,
        source_lang: Optional[str] = None,
        target_lang: str = "eng_Latn",
    ) -> TranslationResult:
        """
        Translate a message synchronously with NLLB via CTranslate2.

        This method is intentionally synchronous because CTranslate2 itself
        exposes a blocking inference call. The public async ``translate``
        method runs it through ``asyncio.to_thread``.
        """
        if not text or not text.strip():
            return self._failure_result(
                text=text or "",
                source_lang=source_lang,
                target_lang=target_lang,
                error="empty_text",
            )

        try:
            resolved_source_lang = self._resolve_source_language(
                text=text,
                source_lang=source_lang,
            )

            if resolved_source_lang is None:
                return self._failure_result(
                    text=text,
                    source_lang=None,
                    target_lang=target_lang,
                    error="language_not_detected_or_unsupported",
                )

            if not self.supports_language(
                source_lang=resolved_source_lang,
                target_lang=target_lang,
            ):
                return self._failure_result(
                    text=text,
                    source_lang=resolved_source_lang,
                    target_lang=target_lang,
                    error="unsupported_language",
                )

            # Translation is not required when the source is already
            # the requested target language.
            if resolved_source_lang == target_lang:
                return TranslationResult(
                    original_text=text,
                    translated_text=text,
                    provider=self.provider_name,
                    used_fallback=True,
                    success=True,
                    source_lang=resolved_source_lang,
                    target_lang=target_lang,
                    error=None,
                )

            with self._translation_lock:
                # NLLB needs to know the source language before tokenization.
                self.tokenizer.src_lang = resolved_source_lang

                source_ids = self.tokenizer.encode(
                    text,
                    add_special_tokens=True,
                )

                source_tokens = (
                    self.tokenizer.convert_ids_to_tokens(
                        source_ids
                    )
                )

                # CTranslate2's official NLLB integration uses the
                # destination FLORES language code directly as prefix.
                target_prefix = [target_lang]

                results = self.translator.translate_batch(
                    [source_tokens],
                    target_prefix=[target_prefix],
                    beam_size=self.beam_size,
                    max_decoding_length=self.max_decoding_length,
                    batch_type="examples",
                )

                if (
                    not results
                    or not results[0].hypotheses
                    or not results[0].hypotheses[0]
                ):
                    return self._failure_result(
                        text=text,
                        source_lang=resolved_source_lang,
                        target_lang=target_lang,
                        error="empty_translation_result",
                    )

                # The first generated token is the forced target-language
                # prefix and must not be included in the final text.
                output_tokens = (
                    results[0].hypotheses[0][1:]
                )

                output_ids = (
                    self.tokenizer.convert_tokens_to_ids(
                        output_tokens
                    )
                )

                translated_text = self.tokenizer.decode(
                    output_ids,
                    skip_special_tokens=True,
                ).strip()

            if not translated_text:
                return self._failure_result(
                    text=text,
                    source_lang=resolved_source_lang,
                    target_lang=target_lang,
                    error="empty_translated_text",
                )

            return TranslationResult(
                original_text=text,
                translated_text=translated_text,
                provider=self.provider_name,
                used_fallback=True,
                success=True,
                source_lang=resolved_source_lang,
                target_lang=target_lang,
                error=None,
            )

        except Exception as exc:
            return self._failure_result(
                text=text,
                source_lang=source_lang,
                target_lang=target_lang,
                error=f"{type(exc).__name__}: {exc}",
            )

    async def translate(
        self,
        text: str,
        source_lang: Optional[str] = None,
        target_lang: str = "eng_Latn",
        **kwargs,
    ) -> TranslationResult:
        """
        Translate without blocking the Telethon/asyncio event loop.
        """
        return await asyncio.to_thread(
            self._translate_sync,
            text,
            source_lang,
            target_lang,
        )
