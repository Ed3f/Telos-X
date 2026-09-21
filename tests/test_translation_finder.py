"""Translation cooldown/fallback and Finder behavior tests."""

import asyncio
import configparser
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from telethon.errors import FloodWaitError

from telos_x.finder.finder_engine import FinderEngine
from telos_x.services.traslation.local_provider import CTranslate2LocalTranslationProvider
from telos_x.services.traslation.schemas import TranslationResult
from telos_x.services.traslation.translation_service import TranslationService


def _result(text, translated, provider='fake', success=True, fallback=False):
    return TranslationResult(
        original_text=text,
        translated_text=translated,
        provider=provider,
        used_fallback=fallback,
        success=success,
    )


class FakeProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def translate(self, text, **kwargs):
        self.calls += 1
        response = self.responses[min(self.calls - 1, len(self.responses) - 1)]
        if isinstance(response, Exception):
            raise response
        return response


@pytest.mark.asyncio
async def test_telegram_translation_success_is_preferred():
    telegram = FakeProvider([_result('ciao', 'hello', provider='telegram')])
    local = FakeProvider([_result('ciao', 'local', fallback=True)])
    service = TranslationService(telegram_provider=telegram, local_provider=local)
    result = await service.translate('ciao')
    assert result.translated_text == 'hello'
    assert local.calls == 0


@pytest.mark.asyncio
async def test_floodwait_immediately_uses_local_and_sets_cooldown():
    telegram = FakeProvider([FloodWaitError(None, capture=2)])
    local = FakeProvider([_result('ciao', 'hello', fallback=True)])
    service = TranslationService(telegram_provider=telegram, local_provider=local)
    result = await service.translate('ciao')
    assert result.translated_text == 'hello'
    assert service.telegram_blocked_until > 0
    await service.translate('ancora')
    assert telegram.calls == 1
    assert local.calls == 2


@pytest.mark.asyncio
async def test_non_flood_failure_uses_local_without_global_cooldown():
    telegram = FakeProvider([_result('ciao', 'ciao', success=False)])
    local = FakeProvider([_result('ciao', 'hello', fallback=True)])
    service = TranslationService(telegram_provider=telegram, local_provider=local)
    result = await service.translate('ciao')
    assert result.translated_text == 'hello'
    assert service.telegram_blocked_until == 0


@pytest.mark.asyncio
async def test_missing_local_provider_degrades_to_original_text():
    telegram = FakeProvider([_result('ciao', 'ciao', success=False)])
    service = TranslationService(telegram_provider=telegram, local_provider=None)
    service.local_provider = None
    result = await service.translate('ciao')
    assert not result.success
    assert result.translated_text == 'ciao'
    assert result.error == 'local_translation_provider_unavailable'


@pytest.mark.asyncio
async def test_empty_text_and_concurrent_requests():
    telegram = FakeProvider([_result('x', 'translated', provider='telegram')])
    service = TranslationService(telegram_provider=telegram, local_provider=telegram)
    empty = await service.translate('   ')
    assert not empty.success and empty.error == 'empty_text'
    results = await asyncio.gather(*(service.translate('x') for _ in range(5)))
    assert all(result.success for result in results)


def test_local_provider_missing_extra_or_model_is_clear(tmp_path):
    with pytest.raises((RuntimeError, FileNotFoundError)):
        CTranslate2LocalTranslationProvider(str(tmp_path / 'missing'))


def test_local_provider_handles_english_and_unsupported_languages_without_inference():
    provider = object.__new__(CTranslate2LocalTranslationProvider)
    provider.provider_name = 'local_ctranslate2_nllb'
    english = provider._translate_sync(
        'already English', source_lang='en', target_lang='eng_Latn'
    )
    unsupported = provider._translate_sync(
        'testo', source_lang='xx', target_lang='eng_Latn'
    )
    assert english.success and english.translated_text == 'already English'
    assert not unsupported.success
    assert unsupported.error == 'language_not_detected_or_unsupported'


def _finder_config():
    config = configparser.ConfigParser(interpolation=None)
    config.read_dict(
        {
            'FINDER': {'enabled': 'true'},
            'FINDER.RULE.Raw': {
                'regex': 'raw-indicator',
                'severity_hint': 'high',
            },
            'FINDER.RULE.Translated': {
                'regex': 'translated-indicator',
                'severity_hint': 'medium',
            },
            'FINDER.RULE.Broken': {'regex': '('},
        }
    )
    return config


@pytest.mark.asyncio
async def test_finder_inspects_original_and_translation_and_skips_bad_regex():
    finder = FinderEngine()
    finder.configure(_finder_config())
    hits = await finder.find_signals(
        SimpleNamespace(raw_text='raw-indicator'),
        raw_text='raw-indicator',
        translation='translated-indicator',
    )
    assert {hit['id'] for hit in hits} == {
        'FINDER.RULE.Raw',
        'FINDER.RULE.Translated',
    }


@pytest.mark.asyncio
async def test_check_host_is_offloaded_for_url_rule():
    config = configparser.ConfigParser(interpolation=None)
    config.read_dict(
        {
            'FINDER': {'enabled': 'true'},
            'FINDER.RULE.MessagesWithURL': {'regex': 'https?://'},
        }
    )
    finder = FinderEngine()
    finder.configure(config)
    with patch('telos_x.finder.finder_engine.check_host', return_value={'ok': True}):
        hits = await finder.find_signals(
            SimpleNamespace(raw_text='https://example.test'),
            raw_text='https://example.test',
        )
    assert hits[0]['response'] == {'ok': True}
