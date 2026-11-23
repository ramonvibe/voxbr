"""Custo por provedor = uso informado pelo LiveKit x tabela de preços (config/prices.yaml)."""

from functools import cache
from pathlib import Path

import yaml

PRICES_FILE = Path(__file__).resolve().parent.parent / "config" / "prices.yaml"


@cache
def prices() -> dict:
    return yaml.safe_load(PRICES_FILE.read_text(encoding="utf-8")) or {}


def cost_usd(usage: list[dict], table: dict | None = None) -> list[dict]:
    """Recebe o uso por modelo (session.usage serializado) e devolve cada item com `cost_usd`.
    Modelo sem preço cadastrado fica com custo None, para o painel sinalizar."""
    table = prices() if table is None else table
    out = []
    for item in usage:
        price = table.get(f"{item.get('provider')}:{item.get('model')}") or table.get(item.get("model", ""))
        cost = None
        if price:
            kind = item.get("type", "")
            if kind.startswith("llm"):
                cost = (
                    item.get("input_tokens", 0) * price.get("input_per_mtok", 0)
                    + item.get("output_tokens", 0) * price.get("output_per_mtok", 0)
                ) / 1e6
            elif kind.startswith("stt"):
                cost = item.get("audio_duration", 0) / 60 * price.get("per_minute", 0)
            elif kind.startswith("tts"):
                if "per_mchar" in price:
                    cost = item.get("characters_count", 0) * price["per_mchar"] / 1e6
                else:
                    cost = item.get("audio_duration", 0) / 60 * price.get("per_minute", 0)
        out.append({**item, "cost_usd": cost})
    return out
