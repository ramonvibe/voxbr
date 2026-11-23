"""Evals: roda conversas de teste (texto) contra combinações de LLM e mede acerto, transbordo, latência e custo.

Uso:
    .venv/bin/python -m evals.runner evals/suites/exemplo.yaml \\
        --llm openai:gpt-4.1-mini --llm google:gemini-2.5-flash --judge openai:gpt-4.1

As regras ("rules.md") e a base de conhecimento vêm do agente indicado na suíte, no banco.
STT e TTS não entram: o texto vai direto ao LLM (ver README, seção Evals).
"""

import argparse
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path

import yaml
from livekit.agents import AgentSession

from apps.agent.main import PhoneAgent, Target
from core import rag
from core.config import DEFAULT_EMBEDDING
from core.db import AgentProfile, Queue, SessionLocal
from core.pricing import cost_usd
from core.providers import registry

REPORTS = Path(__file__).resolve().parent / "reports"
ALWAYS_CLOSED = {"days": {d: [] for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}}


def spec(text: str) -> dict:
    vendor, _, model = text.partition(":")
    if not model:
        raise SystemExit(f"use fornecedor:modelo (recebi '{text}')")
    return {"vendor": vendor, "model": model}


def load_agent(agent_id: int) -> AgentProfile:
    with SessionLocal() as db:
        agent = db.get(AgentProfile, agent_id)
    if agent is None:
        raise SystemExit(f"agente {agent_id} não existe no banco")
    agent.embedding = agent.embedding or DEFAULT_EMBEDDING
    return agent


def check(case: dict, transfers: list[dict], judged_ok: bool | None) -> tuple[bool, list[str]]:
    """Compara o que aconteceu com o `expect` do caso. Função pura (testada em tests/test_evals.py)."""
    expect = case.get("expect", {})
    problems = []
    if "transfer" in expect and bool(transfers) != expect["transfer"]:
        problems.append("esperava transbordo" if expect["transfer"] else "transbordou sem precisar")
    if expect.get("reason") and transfers and transfers[0].get("reason") != expect["reason"]:
        problems.append(f"motivo {transfers[0].get('reason')} != {expect['reason']}")
    if judged_ok is False:
        problems.append("juiz reprovou a resposta")
    return not problems, problems


async def run_case(agent: AgentProfile, llm_spec: dict, case: dict, queue_open: bool, judge) -> dict:
    queue = Queue(id=0, name="eval", hours={} if queue_open else ALWAYS_CLOSED, holidays=[], wait_timeout_s=60)
    phone_agent = PhoneAgent(None, Target(did="", number_id=None, mode="ai", agent=agent, queue=queue),
                             None, caller="", transcript=[], knowledge=rag.inline_knowledge(agent))
    llm = registry.build_llm([llm_spec], agent.language)
    transfers, latencies, last = [], [], None
    async with AgentSession(llm=llm) as session:
        await session.start(phone_agent)
        for turn in case["turns"]:
            started = time.perf_counter()
            last = await session.run(user_input=turn)
            latencies.append(time.perf_counter() - started)
            for ev in last.events:
                if ev.type == "function_call" and ev.item.name == "transfer_to_human":
                    transfers.append(json.loads(ev.item.arguments or "{}"))
        judged_ok = None
        if judge and case.get("expect", {}).get("judge"):
            try:
                # Julga a última fala do agente (ignora chamadas de ferramenta depois dela).
                idx = max(i for i, ev in enumerate(last.events) if ev.type == "message")
                await last.expect[idx].is_message(role="assistant").judge(judge, intent=case["expect"]["judge"])
                judged_ok = True
            except (AssertionError, ValueError):  # ValueError: o agente não falou nada
                judged_ok = False
        usage = cost_usd([u.model_dump() for u in session.usage.model_usage])
    ok, problems = check(case, transfers, judged_ok)
    return {
        "case": case["name"], "llm": f"{llm_spec['vendor']}:{llm_spec['model']}", "ok": ok, "problems": problems,
        "transferred": bool(transfers),
        "reply": next((ev.item.text_content for ev in reversed(last.events) if ev.type == "message"), None) if last else None,
        "latency_s": sum(latencies) / len(latencies),
        "cost_usd": sum(u["cost_usd"] or 0 for u in usage),
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("suite")
    parser.add_argument("--llm", action="append", required=True, help="fornecedor:modelo (repita para comparar)")
    parser.add_argument("--judge", help="fornecedor:modelo do juiz (opcional; sem juiz só checa transbordo)")
    args = parser.parse_args()

    suite = yaml.safe_load(Path(args.suite).read_text(encoding="utf-8"))
    agent = load_agent(suite["agent_id"])
    judge = registry.build_llm([spec(args.judge)], agent.language) if args.judge else None
    results = []
    for llm_text in args.llm:
        for case in suite["cases"]:
            res = await run_case(agent, spec(llm_text), case, case.get("queue_open", suite.get("queue_open", True)), judge)
            results.append(res)
            mark = "OK " if res["ok"] else "ERRO"
            print(f"[{mark}] {res['llm']:32} {res['case']:40} {res['latency_s']:.2f}s  "
                  f"US$ {res['cost_usd']:.5f}  {'; '.join(res['problems'])}")

    print("\nResumo por modelo:")
    for llm_text in args.llm:
        rows = [r for r in results if r["llm"] == llm_text]
        print(f"  {llm_text:32} acerto {sum(r['ok'] for r in rows)}/{len(rows)}  "
              f"transbordo {sum(r['transferred'] for r in rows) / len(rows):.0%}  "
              f"latência média {sum(r['latency_s'] for r in rows) / len(rows):.2f}s  "
              f"custo total US$ {sum(r['cost_usd'] for r in rows):.4f}")
    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / f"{Path(args.suite).stem}-{datetime.now():%Y%m%d-%H%M%S}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\nRelatório: {out}")


if __name__ == "__main__":
    asyncio.run(main())
