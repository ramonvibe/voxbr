"""Teste de ponta a ponta do transbordo, sem microfone (texto no lugar da voz).

Pré-requisitos: API em :8000 e worker rodando (`apps/agent/main.py dev`), .env preenchido.
Uso: .venv/bin/python scripts/smoke_handoff.py <number_id>

Fluxo: liga para o número pelo navegador simulado -> pede atendente -> confere a fila no console ->
aceita como atendente -> confere que a IA saiu -> encerra -> confere transcrição e custo.
"""

import asyncio
import os
import sys

import httpx
from dotenv import load_dotenv
from livekit import rtc

load_dotenv()
API = "http://127.0.0.1:8000/api"


async def wait_for(predicate, timeout: float, what: str):
    for _ in range(int(timeout * 2)):
        result = await predicate()
        if result:
            return result
        await asyncio.sleep(0.5)
    raise SystemExit(f"FALHOU: {what} (timeout {timeout}s)")


async def main(number_id: int) -> None:
    async with httpx.AsyncClient(base_url=API, timeout=30) as http:
        r = await http.post("/auth/login", json={"email": os.environ["ADMIN_EMAIL"], "password": os.environ["ADMIN_PASSWORD"]})
        r.raise_for_status()
        call = (await http.post("/test-call", json={"number_id": number_id})).json()

        client = rtc.Room()
        await client.connect(call["server_url"], call["token"])
        agent_ids = set()
        await wait_for(lambda: _agent_present(client, agent_ids), 30, "agente entrar na sala")
        print("ok: agente entrou na sala")
        # Espera o aviso LGPD (não interrompível) e a saudação terminarem antes de "falar".
        await asyncio.sleep(2)
        await wait_for(lambda: _agent_listening(client, agent_ids), 60, "agente terminar o aviso")
        await asyncio.sleep(1.5)
        await wait_for(lambda: _agent_listening(client, agent_ids), 60, "agente terminar a saudação")
        await client.local_participant.send_text("Quero falar com um atendente, por favor.", topic="lk.chat")

        async def waiting():
            state = (await http.get("/console")).json()
            return next((c for c in state["waiting"] if c["room"] == call["room"]), None)

        queued = await wait_for(waiting, 60, "chamada aparecer na fila do console")
        print(f"ok: na fila. motivo={queued['transfer_reason']} resumo={queued['summary']!r}")

        accepted = (await http.post(f"/console/calls/{queued['id']}/accept")).json()
        attendant = rtc.Room()
        await attendant.connect(accepted["server_url"], accepted["token"])

        async def agent_left():
            return not (set(client.remote_participants) & agent_ids)

        await wait_for(agent_left, 30, "agente sair depois que o atendente entrou")
        print("ok: atendente entrou e o agente saiu")

        await http.post(f"/console/calls/{queued['id']}/hangup")
        await asyncio.sleep(3)
        final = (await http.get(f"/calls/{queued['id']}")).json()
        print(f"ok: status={final['status']} falas={len(final['transcript'])} custo=US$ {final['cost_usd']:.5f}")
        for t in final["transcript"]:
            print(f"   {t['role']:9} {t['text']}")
        await attendant.disconnect()
        await client.disconnect()


async def _agent_listening(room: rtc.Room, agent_ids: set) -> bool:
    return any(room.remote_participants[i].attributes.get("lk.agent.state") == "listening"
               for i in agent_ids if i in room.remote_participants)


async def _agent_present(room: rtc.Room, agent_ids: set) -> bool:
    for identity, p in room.remote_participants.items():
        if p.kind == rtc.ParticipantKind.PARTICIPANT_KIND_AGENT:
            agent_ids.add(identity)
    return bool(agent_ids)


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1])))
