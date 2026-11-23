"""Regras de transbordo para humano. Funções puras: testáveis sem chamada, banco ou LLM."""

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DEFAULT_TZ = "America/Sao_Paulo"

REASONS = ("customer_request", "out_of_scope", "no_answer", "provider_failure")


def is_open(hours: dict | None, holidays: list[str] | None, at: datetime) -> bool:
    """hours = {"tz": ..., "days": {"mon": [["08:00", "18:00"]], ...}}. Sem horário configurado = sempre aberto."""
    if not hours or not hours.get("days"):
        return True
    local = at.astimezone(ZoneInfo(hours.get("tz") or DEFAULT_TZ))
    if local.date().isoformat() in (holidays or []):
        return False
    hhmm = local.strftime("%H:%M")
    return any(start <= hhmm < end for start, end in hours["days"].get(DAYS[local.weekday()], []))


@dataclass(frozen=True)
class Decision:
    action: str  # transfer | take_message
    reason: str


def decide(*, queue_id: int | None, hours: dict | None, holidays: list[str] | None, at: datetime) -> Decision:
    """O que fazer quando o agente (ou o cliente) pede um humano."""
    if queue_id is None:
        return Decision("take_message", "sem fila configurada para este número")
    if not is_open(hours, holidays, at):
        return Decision("take_message", "fora do horário de atendimento")
    return Decision("transfer", "fila aberta")
