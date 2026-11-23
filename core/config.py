"""Tipos de configuração compartilhados. Os valores vêm do banco (editados no painel)."""

import re

from pydantic import BaseModel


class ProviderSpec(BaseModel):
    vendor: str
    model: str
    options: dict = {}


DEFAULT_STT = [{"vendor": "openai", "model": "gpt-live-transcribe"}]
DEFAULT_LLM = [{"vendor": "openai", "model": "gpt-4.1-mini"}]
DEFAULT_TTS = [
    {
        "vendor": "openai",
        "model": "gpt-4o-mini-tts",
        "options": {
            "voice": "coral",
            "instructions": "Fale em português do Brasil, com sotaque brasileiro natural e tom cordial.",
        },
    }
]
DEFAULT_EMBEDDING = {"vendor": "openai", "model": "text-embedding-3-small"}


def normalize_did(did: str) -> str:
    """'+55 (31) 99999-0000' -> '+5531999990000'."""
    return "+" + re.sub(r"\D", "", did)
