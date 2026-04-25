from telethon import functions, types
from telethon.errors import FloodWaitError

from .base_provider import BaseTranslationProvider
from .schemas import TranslationResult


class TelegramTranslationProvider(BaseTranslationProvider):
    provider_name = "telegram"

    def supports_language(self, source_lang: str | None, target_lang: str = "eng_Latn") -> bool:
        # Telegram lo trattiamo come provider generico
        return True

    async def translate(
        self,
        text: str,
        source_lang: str | None = None,
        target_lang: str = "eng_Latn",
        **kwargs
    ) -> TranslationResult:
        client = kwargs.get("client")

        if not text:
            return TranslationResult(
                original_text="",
                translated_text="",
                provider=self.provider_name,
                used_fallback=False,
                success=False,
                source_lang=source_lang,
                target_lang=target_lang,
                error="empty_text",
            )

        if client is None:
            return TranslationResult(
                original_text=text,
                translated_text=text,
                provider=self.provider_name,
                used_fallback=False,
                success=False,
                source_lang=source_lang,
                target_lang=target_lang,
                error="missing_client",
            )

        try:
            # Per Telegram target = en
            result = await client(
                functions.messages.TranslateTextRequest(
                    to_lang="en",
                    peer=None,
                    id=None,
                    text=[
                        types.TextWithEntities(
                            text=text,
                            entities=[
                                types.MessageEntityUnknown(
                                    offset=0,
                                    length=min(len(text), 1)
                                )
                            ]
                        )
                    ]
                )
            )

            translated = text
            for item in result.result:
                translated = item.text

            return TranslationResult(
                original_text=text,
                translated_text=translated or text,
                provider=self.provider_name,
                used_fallback=False,
                success=True,
                source_lang=source_lang,
                target_lang=target_lang,
                error=None,
            )

        except FloodWaitError:
            raise

        except Exception as exc:
            return TranslationResult(
                original_text=text,
                translated_text=text,
                provider=self.provider_name,
                used_fallback=False,
                success=False,
                source_lang=source_lang,
                target_lang=target_lang,
                error=str(exc),
            )