from pathlib import Path
from typing import Optional, Dict

import ctranslate2
import transformers
from langdetect import detect, LangDetectException

from .base_provider import BaseTranslationProvider
from .schemas import TranslationResult


class CTranslate2LocalTranslationProvider(BaseTranslationProvider):
    """
    Provider locale multilingua basato su CTranslate2 + NLLB.

    Idea:
    - un solo modello multilingua
    - detection lingua sorgente
    - traduzione sempre verso inglese (eng_Latn)
    - esecuzione preferibilmente su GPU
    """

    provider_name = "local_ctranslate2_nllb"

    # mapping ISO semplificato -> codice NLLB
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
        hf_tokenizer_name: str,
        device: str = "cuda",
        compute_type: str = "float16",
        inter_threads: int = 1,
        intra_threads: int = 0,
        beam_size: int = 4,
        max_decoding_length: int = 256,
    ):
        self.model_path = str(Path(model_path))
        self.hf_tokenizer_name = hf_tokenizer_name
        self.device = device
        self.compute_type = compute_type
        self.beam_size = beam_size
        self.max_decoding_length = max_decoding_length

        self.tokenizer = transformers.AutoTokenizer.from_pretrained(
            self.hf_tokenizer_name
        )

        self.translator = ctranslate2.Translator(
            self.model_path,
            device=self.device,
            compute_type=self.compute_type,
            inter_threads=inter_threads,
            intra_threads=intra_threads,
        )

    def _detect_language(self, text: str) -> Optional[str]:
        """
        Rileva la lingua con langdetect e la converte in codice NLLB.
        """
        try:
            lang = detect(text)
            return self.LANG_MAP.get(lang)
        except LangDetectException:
            return None
        except Exception:
            return None

    def supports_language(self, source_lang: Optional[str], target_lang: str = "eng_Latn") -> bool:
        """
        Verifica se la lingua sorgente è supportata dal mapping NLLB configurato.
        """
        if source_lang is None:
            return False
        return source_lang in self.LANG_MAP.values()

    async def translate(
        self,
        text: str,
        source_lang: Optional[str] = None,
        target_lang: str = "eng_Latn",
        **kwargs
    ) -> TranslationResult:
        """
        Traduce il testo con NLLB via CTranslate2.
        """
        if not text or not text.strip():
            return TranslationResult(
                original_text=text or "",
                translated_text=text or "",
                provider=self.provider_name,
                used_fallback=True,
                success=False,
                source_lang=source_lang,
                target_lang=target_lang,
                error="empty_text",
            )

        try:
            # Se non viene passata la lingua, la rileviamo
            resolved_source_lang = source_lang or self._detect_language(text)

            # Se non la rileviamo, non possiamo costruire il prefisso corretto NLLB
            if resolved_source_lang is None:
                return TranslationResult(
                    original_text=text,
                    translated_text=text,
                    provider=self.provider_name,
                    used_fallback=True,
                    success=False,
                    source_lang=None,
                    target_lang=target_lang,
                    error="language_not_detected",
                )

            if not self.supports_language(resolved_source_lang, target_lang):
                return TranslationResult(
                    original_text=text,
                    translated_text=text,
                    provider=self.provider_name,
                    used_fallback=True,
                    success=False,
                    source_lang=resolved_source_lang,
                    target_lang=target_lang,
                    error="unsupported_language",
                )

            # Per NLLB va impostata la lingua sorgente nel tokenizer
            self.tokenizer.src_lang = resolved_source_lang

            # Tokenizzazione del testo sorgente
            source_ids = self.tokenizer.encode(text, add_special_tokens=True)
            source_tokens = self.tokenizer.convert_ids_to_tokens(source_ids)

            # Target prefix NLLB: lingua target in token
            target_prefix_ids = self.tokenizer.encode(
                target_lang,
                add_special_tokens=False
            )
            target_prefix_tokens = self.tokenizer.convert_ids_to_tokens(target_prefix_ids)

            # Inferenza CTranslate2
            results = self.translator.translate_batch(
                [source_tokens],
                target_prefix=[target_prefix_tokens],
                beam_size=self.beam_size,
                max_decoding_length=self.max_decoding_length,
                batch_type="examples",
            )

            output_tokens = results[0].hypotheses[0]

            translated_text = self.tokenizer.decode(
                self.tokenizer.convert_tokens_to_ids(output_tokens),
                skip_special_tokens=True,
            )

            return TranslationResult(
                original_text=text,
                translated_text=translated_text if translated_text else text,
                provider=self.provider_name,
                used_fallback=True,
                success=True,
                source_lang=resolved_source_lang,
                target_lang=target_lang,
                error=None,
            )

        except Exception as exc:
            return TranslationResult(
                original_text=text,
                translated_text=text,
                provider=self.provider_name,
                used_fallback=True,
                success=False,
                source_lang=source_lang,
                target_lang=target_lang,
                error=str(exc),
            )