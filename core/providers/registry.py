"""ProviderSpec (config) -> instância de provedor. Os tipos de interface são os do LiveKit (stt.STT, llm.LLM, tts.TTS).

Uma lista com mais de um spec vira FallbackAdapter: se o primeiro falhar, a chamada segue com o próximo.
"""

from livekit.agents import inference, llm, stt, tts
from livekit.plugins import google, openai

from core.config import ProviderSpec

# Novo fornecedor = nova entrada aqui; o núcleo não muda.
_STT = {
    "openai": lambda s, lang: openai.STT(model=s.model, language=lang, **s.options),
    "google": lambda s, lang: google.STT(model=s.model, languages=[_bcp47(lang)], **s.options),
    # LiveKit Inference: cobra na conta LiveKit, sem chave do fornecedor. model = "deepgram/nova-3", etc.
    "livekit": lambda s, lang: inference.STT(s.model, language=lang, **s.options),
}
_LLM = {
    "openai": lambda s, lang: openai.LLM(model=s.model, **s.options),
    "google": lambda s, lang: google.LLM(model=s.model, **s.options),
    "livekit": lambda s, lang: inference.LLM(s.model, **s.options),
}
_REALTIME = {
    "openai": lambda s, lang: openai.realtime.RealtimeModel(model=s.model, **_openai_realtime_options(s.options)),
    "google": lambda s, lang: google.realtime.RealtimeModel(model=s.model, language=_bcp47(lang), **s.options),
}


def _openai_realtime_options(options: dict) -> dict:
    """turn_detection vem do banco como dict (ex.: {"type": "semantic_vad", "eagerness": "high"}); o plugin quer o tipo."""
    if isinstance(options.get("turn_detection"), dict):
        from openai.types.realtime.realtime_audio_input_turn_detection import RealtimeAudioInputTurnDetection
        from pydantic import TypeAdapter

        td = TypeAdapter(RealtimeAudioInputTurnDetection).validate_python(options["turn_detection"])
        options = options | {"turn_detection": td}
    return options


_TTS = {
    "openai": lambda s, lang: openai.TTS(model=s.model, **s.options),
    "google": lambda s, lang: google.TTS(language=_bcp47(lang), **({"voice_name": s.model} | s.options)),
    "livekit": lambda s, lang: inference.TTS(s.model, language=lang, **s.options),
}

# Exibido no painel como sugestão; qualquer modelo aceito pelo fornecedor funciona.
CATALOG = {
    "stt": {"openai": ["gpt-live-transcribe", "gpt-transcribe"], "google": ["chirp_3"],
            "livekit": ["deepgram/nova-3", "assemblyai/universal-streaming-multilingual", "cartesia/ink-2"]},
    "llm": {"openai": ["gpt-4.1-mini", "gpt-5.4-mini", "gpt-4.1"], "google": ["gemini-2.5-flash", "gemini-3.8-flash"],
            "livekit": ["openai/gpt-4.1-mini", "google/gemini-2.5-flash", "openai/gpt-5.4-mini"]},
    "tts": {"openai": ["gpt-4o-mini-tts"], "google": ["pt-BR-Chirp3-HD-Aoede", "pt-BR-Chirp3-HD-Charon"],
            "livekit": ["cartesia/sonic-3", "deepgram/aura-2", "inworld/inworld-tts-1.5-mini"]},
    "realtime": {"openai": ["gpt-realtime"], "google": ["gemini-3.8-live", "gemini-2.5-flash-native-audio-preview-12-2025"]},
    "embedding": {"openai": ["text-embedding-3-small", "text-embedding-3-large"], "google": ["gemini-embedding-001"]},
}


def _bcp47(lang: str) -> str:
    return "pt-BR" if lang == "pt" else lang


def _build_one(table: dict, kind: str, spec: ProviderSpec | dict, language: str):
    spec = ProviderSpec.model_validate(spec)
    try:
        factory = table[spec.vendor]
    except KeyError:
        raise ValueError(f"{kind}: fornecedor '{spec.vendor}' não registrado ({sorted(table)})") from None
    return factory(spec, language)


def _build(table: dict, kind: str, specs, language: str, fallback):
    specs = specs if isinstance(specs, list) else [specs]
    if not specs:
        raise ValueError(f"{kind}: nenhum provedor configurado")
    built = [_build_one(table, kind, s, language) for s in specs]
    return built[0] if len(built) == 1 else fallback(built)


def build_stt(specs, language: str, vad=None) -> stt.STT:
    return _build(_STT, "stt", specs, language, lambda b: stt.FallbackAdapter(b, vad=vad))


def build_llm(specs, language: str) -> llm.LLM:
    return _build(_LLM, "llm", specs, language, llm.FallbackAdapter)


def build_realtime(specs, language: str) -> llm.RealtimeModel:
    """Speech-to-speech. Sem fallback no meio da chamada: se não der para montar, o worker cai para o pipeline."""
    return _build_one(_REALTIME, "realtime", (specs if isinstance(specs, list) else [specs])[0], language)


def build_tts(specs, language: str) -> tts.TTS:
    return _build(_TTS, "tts", specs, language, tts.FallbackAdapter)
