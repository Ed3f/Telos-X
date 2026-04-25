from abc import ABC, abstractmethod
from typing import Optional

from .schemas import TranslationResult


class BaseTranslationProvider(ABC):
    """
    Contratto base per tutti i provider di traduzione.

    Ogni provider:
    - dichiara un nome
    - può decidere se supporta o meno una lingua
    - implementa la traduzione verso una lingua target
    """

    provider_name: str = "base"

    @abstractmethod
    def supports_language(self, source_lang: Optional[str], target_lang: str = "eng_Latn") -> bool:
        """
        Ritorna True se il provider supporta la lingua sorgente richiesta.
        """
        raise NotImplementedError

    @abstractmethod
    async def translate(
        self,
        text: str,
        source_lang: Optional[str] = None,
        target_lang: str = "eng_Latn",
        **kwargs
    ) -> TranslationResult:
        """
        Traduce il testo e restituisce un TranslationResult standardizzato.
        """
        raise NotImplementedError