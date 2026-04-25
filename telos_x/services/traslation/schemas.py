from dataclasses import dataclass
from typing import Optional


@dataclass
class TranslationResult:
    """
    Risultato standardizzato della traduzione.
    """

    original_text: str
    translated_text: str
    provider: str
    used_fallback: bool
    success: bool

    source_lang: Optional[str] = None
    target_lang: Optional[str] = "eng_Latn"

    error: Optional[str] = None