from datetime import datetime, timezone

import pytest

from core import auth, handoff, lgpd, pricing, rag
from core.handoff import decide, is_open

UTC = timezone.utc
HOURS = {"tz": "America/Sao_Paulo", "days": {"mon": [["08:00", "12:00"], ["14:00", "18:00"]], "tue": [["08:00", "18:00"]]}}


# ---------- handoff ----------


def test_is_open_empty_hours_always_open():
    at = datetime(2026, 1, 4, 3, tzinfo=UTC)
    assert is_open(None, None, at) and is_open({}, [], at) and is_open({"days": {}}, [], at)


def test_is_open_ranges_and_tz():
    # 2026-01-05 é segunda. 12:00 UTC = 09:00 em São Paulo (UTC-3).
    assert is_open(HOURS, [], datetime(2026, 1, 5, 12, 0, tzinfo=UTC))
    assert not is_open(HOURS, [], datetime(2026, 1, 5, 8, 0, tzinfo=UTC))  # 05:00 local
    assert not is_open(HOURS, [], datetime(2026, 1, 5, 16, 0, tzinfo=UTC))  # 13:00 local, intervalo
    assert is_open(HOURS, [], datetime(2026, 1, 5, 17, 0, tzinfo=UTC))  # 14:00 local
    assert not is_open(HOURS, [], datetime(2026, 1, 5, 21, 0, tzinfo=UTC))  # 18:00 local: fim exclusivo
    assert is_open(HOURS, [], datetime(2026, 1, 5, 11, 0, tzinfo=UTC))  # 08:00 local: início inclusivo


def test_is_open_day_missing_closed_and_tz_changes_weekday():
    assert not is_open(HOURS, [], datetime(2026, 1, 7, 15, tzinfo=UTC))  # quarta
    # terça 01:00 UTC ainda é segunda 22:00 local
    assert not is_open(HOURS, [], datetime(2026, 1, 6, 1, 0, tzinfo=UTC))


def test_is_open_holiday():
    at = datetime(2026, 1, 5, 12, tzinfo=UTC)
    assert not is_open(HOURS, ["2026-01-05"], at)
    assert is_open(HOURS, ["2026-01-06"], at)


def test_decide():
    at = datetime(2026, 1, 5, 12, tzinfo=UTC)
    assert decide(queue_id=None, hours=HOURS, holidays=[], at=at).action == "take_message"
    assert decide(queue_id=1, hours=HOURS, holidays=[], at=at).action == "transfer"
    assert decide(queue_id=1, hours=HOURS, holidays=["2026-01-05"], at=at).action == "take_message"
    assert decide(queue_id=1, hours=None, holidays=None, at=at).action == "transfer"


# ---------- lgpd ----------


def test_redact_cpf():
    assert lgpd.redact("meu cpf 529.982.247-25 ok") == "meu cpf [cpf] ok"
    assert lgpd.redact("52998224725") == "[cpf]"
    assert "529.982.247-26" in lgpd.redact("cpf 529.982.247-26")  # dígito inválido
    assert lgpd.redact("111.111.111-11") == "111.111.111-11"


def test_redact_email_phone_cnpj_cep():
    assert lgpd.redact("a.b+c@x.com.br") == "[email]"
    assert lgpd.redact("ligue (31) 99999-0000") == "ligue [telefone]"
    assert lgpd.redact("+55 31 99999-0000") == "[telefone]"
    assert lgpd.redact("cnpj 11.222.333/0001-81") == "cnpj [cnpj]"
    assert lgpd.redact("CEP 30140-071") == "CEP [cep]"


def test_redact_card_luhn():
    assert lgpd.redact("cartão 4539 1488 0343 6467") == "cartão [cartao]"
    assert "4539 1488 0343 6468" in lgpd.redact("cartão 4539 1488 0343 6468")
    assert lgpd.redact("nada sensível") == "nada sensível"


def test_redacting_filter():
    import logging
    rec = logging.LogRecord("x", logging.INFO, "", 0, "email %s", ("a@b.com",), None)
    assert lgpd.RedactingFilter().filter(rec)
    assert rec.msg == "email [email]" and rec.args is None


# ---------- pricing ----------


TABLE = {
    "gpt-x": {"input_per_mtok": 1.0, "output_per_mtok": 4.0},
    "openai:stt": {"per_minute": 0.006},
    "tts-char": {"per_mchar": 15.0},
    "tts-min": {"per_minute": 0.015},
}


def test_cost_usd():
    usage = [
        {"type": "llm_usage", "provider": "openai", "model": "gpt-x", "input_tokens": 1_000_000, "output_tokens": 500_000},
        {"type": "stt_usage", "provider": "openai", "model": "stt", "audio_duration": 120},
        {"type": "tts_usage", "model": "tts-char", "characters_count": 2_000_000},
        {"type": "tts_usage", "model": "tts-min", "audio_duration": 60},
        {"type": "llm_usage", "model": "desconhecido", "input_tokens": 5},
    ]
    out = pricing.cost_usd(usage, TABLE)
    assert [o["cost_usd"] for o in out[:4]] == pytest.approx([3.0, 0.012, 30.0, 0.015])
    assert out[4]["cost_usd"] is None
    assert pricing.cost_usd([], TABLE) == []


def test_cost_usd_default_table_loads():
    assert pricing.cost_usd([{"type": "llm", "model": "gpt-4.1-mini", "input_tokens": 1_000_000}])[0]["cost_usd"] == pytest.approx(0.4)


# ---------- rag.chunk_text ----------


def test_chunk_empty():
    assert rag.chunk_text("") == [] and rag.chunk_text(" \n\n  \n") == []


def test_chunk_small_single():
    assert rag.chunk_text("olá\n\nmundo") == ["olá mundo"]


def test_chunk_sizes_bounded_no_empty():
    text = "\n".join(f"Parágrafo número {i} " + "palavra " * 30 for i in range(80))
    chunks = rag.chunk_text(text, size=500, overlap=50)
    assert len(chunks) > 3
    assert all(c.strip() for c in chunks)
    assert all(len(c) <= 500 for c in chunks)


def test_chunk_overlap_between_chunks():
    text = "\n".join(f"frase{i:03d} " + "x" * 40 for i in range(40))
    chunks = rag.chunk_text(text, size=300, overlap=60)
    for a, b in zip(chunks, chunks[1:]):
        assert b.startswith(a[-60:].lstrip()) or a[-20:] in b


def test_chunk_long_paragraph_split_with_overlap():
    p = "".join(chr(97 + i % 26) for i in range(2500))
    chunks = rag.chunk_text(p, size=1000, overlap=100)
    assert len(chunks) >= 3 and all(len(c) <= 1000 for c in chunks)
    assert chunks[0][-100:] == chunks[1][:100]


# ---------- auth ----------


def test_password_hash_verify():
    h = auth.hash_password("segredo123")
    assert h != auth.hash_password("segredo123")  # salt
    assert auth.verify_password("segredo123", h)
    assert not auth.verify_password("outra", h)
    assert not auth.verify_password("x", "lixo")


def test_session_roundtrip_and_tamper():
    tok = auth.issue_session(42)
    assert auth.read_session(tok) == 42
    head, payload, sig = tok.split(".")
    assert auth.read_session(f"{head}.{payload}.{sig[:-2]}AA") is None
    assert auth.read_session("") is None
    assert auth.read_session("a.b.c") is None


def test_session_expired(monkeypatch):
    import time
    real = time.time()
    monkeypatch.setattr(auth.time, "time", lambda: real - 2 * auth.SESSION_TTL_S)
    assert auth.read_session(auth.issue_session(1)) is None


def test_session_wrong_secret(monkeypatch):
    tok = auth.issue_session(1)
    monkeypatch.setenv("SESSION_SECRET", "outro-segredo-outro-segredo-outro!!")
    assert auth.read_session(tok) is None


def test_chunk_heading_starts_new_chunk():
    chunks = rag.chunk_text("## A\ntexto a\n\n## B\ntexto b", size=1200)
    assert chunks == ["## A texto a", "## B texto b"]
    assert "texto a" not in chunks[1]  # sem overlap atravessando o título
