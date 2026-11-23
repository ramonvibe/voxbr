"""LGPD: mascaramento de dados pessoais nos logs e expurgo por prazo de retenção."""

import logging
import re
from datetime import timedelta

from sqlalchemy import select

from core.db import Call, Message, PhoneNumber, SessionLocal, now


def _cpf_valid(digits: str) -> bool:
    if len(digits) != 11 or len(set(digits)) == 1:
        return False
    for n in (9, 10):
        total = sum(int(d) * (n + 1 - i) for i, d in enumerate(digits[:n]))
        if (total * 10 % 11) % 10 != int(digits[n]):
            return False
    return True


def _luhn_valid(digits: str) -> bool:
    total = 0
    for i, d in enumerate(reversed(digits)):
        n = int(d) * (2 if i % 2 else 1)
        total += n - 9 if n > 9 else n
    return total % 10 == 0


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_CNPJ = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_PHONE = re.compile(r"(?:\+?55\s?)?\(?\b\d{2}\)?\s?9?\d{4}[-\s]?\d{4}\b")
_CEP = re.compile(r"\b\d{5}-\d{3}\b")


def redact(text: str) -> str:
    text = _EMAIL.sub("[email]", text)
    text = _CNPJ.sub("[cnpj]", text)
    text = _CPF.sub(lambda m: "[cpf]" if _cpf_valid(re.sub(r"\D", "", m.group())) else m.group(), text)
    text = _CARD.sub(lambda m: "[cartao]" if _luhn_valid(re.sub(r"\D", "", m.group())) else m.group(), text)
    text = _PHONE.sub("[telefone]", text)
    return _CEP.sub("[cep]", text)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = None
        return True


def install_log_redaction() -> None:
    """Aplica o mascaramento em todos os handlers do logger raiz (inclusive os criados depois, via filtro no logger)."""
    root = logging.getLogger()
    root.addFilter(RedactingFilter())
    for handler in root.handlers:
        handler.addFilter(RedactingFilter())


def purge_expired() -> int:
    """Apaga transcrições e recados além do prazo de retenção de cada número. Rodar diariamente (cron)."""
    removed = 0
    with SessionLocal() as db:
        for number in db.scalars(select(PhoneNumber)):
            cutoff = now() - timedelta(days=number.retention_days)
            calls = db.scalars(select(Call).where(Call.number_id == number.id, Call.started_at < cutoff)).all()
            for call in calls:
                for msg in db.scalars(select(Message).where(Message.call_id == call.id)):
                    db.delete(msg)
                db.delete(call)
            removed += len(calls)
        db.commit()
    return removed


if __name__ == "__main__":
    print(f"chamadas expurgadas: {purge_expired()}")
