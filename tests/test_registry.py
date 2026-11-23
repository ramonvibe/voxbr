import pytest
from livekit.agents import llm, stt, tts

from core.embeddings import build_embedding, embedding_model_id
from core.providers import registry


@pytest.fixture(autouse=True)
def fake_keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("GOOGLE_API_KEY", "test")


OPENAI_LLM = {"vendor": "openai", "model": "gpt-4.1-mini"}
GOOGLE_LLM = {"vendor": "google", "model": "gemini-2.5-flash"}


def test_single_spec_builds_plain_provider():
    built = registry.build_llm([OPENAI_LLM], "pt")
    assert not isinstance(built, llm.FallbackAdapter)
    assert built.model == "gpt-4.1-mini"


def test_two_specs_build_fallback_in_order():
    built = registry.build_llm([OPENAI_LLM, GOOGLE_LLM], "pt")
    assert isinstance(built, llm.FallbackAdapter)
    assert [x.model for x in built._llm_instances] == ["gpt-4.1-mini", "gemini-2.5-flash"]


def test_stt_and_tts_fallback():
    from livekit.plugins import silero

    # STT sem streaming no fallback exige VAD (o worker sempre passa o dele)
    s = registry.build_stt([{"vendor": "openai", "model": "gpt-transcribe"},
                            {"vendor": "openai", "model": "gpt-4o-mini-transcribe"}], "pt", vad=silero.VAD.load())
    t = registry.build_tts([{"vendor": "openai", "model": "gpt-4o-mini-tts"},
                            {"vendor": "openai", "model": "tts-1"}], "pt")
    assert isinstance(s, stt.FallbackAdapter)
    assert isinstance(t, tts.FallbackAdapter)


def test_unknown_vendor_and_empty_list_fail_clearly():
    with pytest.raises(ValueError, match="não registrado"):
        registry.build_llm([{"vendor": "acme", "model": "x"}], "pt")
    with pytest.raises(ValueError, match="nenhum provedor"):
        registry.build_tts([], "pt")


def test_realtime_builds_first_spec_only():
    model = registry.build_realtime([{"vendor": "openai", "model": "gpt-realtime"}], "pt")
    assert isinstance(model, llm.RealtimeModel)


def test_embedding_model_id_is_stable_without_client():
    assert embedding_model_id({"vendor": "openai", "model": "text-embedding-3-small"}) == "openai:text-embedding-3-small"
    assert build_embedding({"vendor": "openai", "model": "text-embedding-3-small"}).model_id == "openai:text-embedding-3-small"
    with pytest.raises(ValueError):
        build_embedding({"vendor": "acme", "model": "x"})


def test_openai_realtime_turn_detection_from_dict():
    from core.providers.registry import _openai_realtime_options

    opts = _openai_realtime_options({"voice": "marin", "turn_detection": {"type": "semantic_vad", "eagerness": "high"}})
    assert opts["voice"] == "marin"
    assert opts["turn_detection"].type == "semantic_vad" and opts["turn_detection"].eagerness == "high"
