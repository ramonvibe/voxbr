"""Worker de voz: atende a chamada (SIP ou navegador), carrega número/agente/fila do banco e conversa em PT-BR.

A cada fala do cliente, a base de conhecimento é consultada antes do LLM (on_user_turn_completed).
Ferramentas do agente: transfer_to_human (fila web), take_message (recado), end_call.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Literal

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    BackgroundAudioPlayer,
    BuiltinAudioClip,
    ChatContext,
    ChatMessage,
    ConversationItemAddedEvent,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    RunContext,
    StopResponse,
    cli,
    function_tool,
    inference,
    metrics,
)
from livekit.agents import llm
from livekit.agents.voice import SpeechHandle
from livekit.plugins import silero
from sqlalchemy import select, update

from core import rag
from core.config import DEFAULT_EMBEDDING, DEFAULT_LLM, DEFAULT_STT, DEFAULT_TTS, normalize_did
from core.db import AgentProfile, Call, Message, PhoneNumber, Queue, SessionLocal, now
from core.handoff import REASONS, decide
from core.lgpd import install_log_redaction
from core.pricing import cost_usd
from core.providers import registry

load_dotenv()
logger = logging.getLogger("voxbr.agent")

ATTENDANT_PREFIX = "atendente-"
# Fala fixa (não depende do LLM): o cliente sempre ouve o aviso, mesmo que o atendente aceite na hora.
TRANSFER_ANNOUNCEMENT = "Vou transferir você para um atendente. Por favor, aguarde na linha."

PLATFORM_RULES = """Você atende ligações telefônicas. Regras fixas da plataforma (valem acima de qualquer outra):
- Fale em português do Brasil, com frases curtas e naturais. Nada de listas, markdown ou emojis.
{knowledge_rule}
- Chame transfer_to_human, com um resumo da conversa, quando: o cliente pedir uma pessoa; o assunto estiver fora das
  regras do operador abaixo; ou o cliente perguntar algo sobre a empresa que a base não responde. Chame direto, sem
  avisar antes: o sistema já anuncia a transferência ao cliente.
- Nunca peça senhas ou dados completos de cartão.
- Quando o cliente se despedir e não houver mais nada a fazer, despeça-se e chame end_call.

Regras do operador:
"""
# pipeline: a busca roda antes do LLM a cada fala (mais rápido). realtime: o modelo responde antes de a transcrição
# chegar, então a busca precisa ser uma ferramenta.
KNOWLEDGE_RULE_PIPELINE = """- A cada fala do cliente, o sistema consulta a base de conhecimento da empresa e entrega o resultado numa mensagem
  "BASE DE CONHECIMENTO". Informações sobre a empresa (produtos, serviços, preços, horários, políticas) só podem vir
  dela. Nunca invente informação."""
KNOWLEDGE_RULE_INLINE = """- Informações sobre a empresa (produtos, serviços, preços, horários, políticas) só podem vir da BASE DE CONHECIMENTO
  no fim destas instruções. Nunca invente informação."""
KNOWLEDGE_RULE_REALTIME = """- Para qualquer pergunta sobre a empresa (produtos, serviços, preços, horários, políticas), chame search_knowledge
  antes de responder e responda só com base no que ela trouxer. Nunca invente informação."""


@dataclass
class Target:
    """O que a chamada usa: carregado do banco uma vez, no início."""

    did: str
    number_id: int | None
    mode: str
    agent: AgentProfile
    queue: Queue | None


def resolve_target(did: str, meta: dict) -> Target:
    with SessionLocal() as db:
        number = None
        if meta.get("number_id"):
            number = db.get(PhoneNumber, meta["number_id"])
        elif did:
            number = db.scalar(select(PhoneNumber).where(PhoneNumber.did == normalize_did(did), PhoneNumber.active))
        agent = None
        if number and number.agent_id:
            agent = db.get(AgentProfile, number.agent_id)
        elif meta.get("agent_id"):
            agent = db.get(AgentProfile, meta["agent_id"])
        if agent is None:
            logger.warning("did=%s sem agente configurado; usando o primeiro agente", did or "web")
            agent = db.scalar(select(AgentProfile).order_by(AgentProfile.id))
        queue = db.get(Queue, number.queue_id) if number and number.queue_id else None
        return Target(did=did, number_id=number.id if number else None, mode=number.mode if number else "ai",
                      agent=agent, queue=queue)


def create_call(room: str, target: Target, caller: str) -> int:
    with SessionLocal() as db:
        call = Call(room=room, did=target.did, caller=caller, number_id=target.number_id,
                    agent_id=target.agent.id if target.agent else None,
                    queue_id=target.queue.id if target.queue else None)
        db.add(call)
        db.commit()
        return call.id


def update_call(call_id: int | None, **values) -> None:
    if call_id is None:  # execução sem chamada real (evals)
        return
    with SessionLocal() as db:
        db.execute(update(Call).where(Call.id == call_id).values(**values))
        db.commit()


def cancel_wait(call_id: int) -> bool:
    """Tira a chamada da fila se ninguém aceitou. False = um atendente aceitou no último instante."""
    with SessionLocal() as db:
        changed = db.execute(
            update(Call).where(Call.id == call_id, Call.status == "waiting_human").values(status="ai")
        ).rowcount
        db.commit()
        return bool(changed)


def finish_call(call_id: int, transcript: list, usage: list) -> None:
    """Grava transcrição e custo. Só encerra se a chamada não estiver com um atendente."""
    with SessionLocal() as db:
        call = db.get(Call, call_id)
        call.transcript, call.usage = transcript, usage
        call.cost_usd = sum(u["cost_usd"] or 0 for u in usage)
        if call.status in ("ai", "waiting_human"):
            call.status, call.ended_at = "ended", now()
        db.commit()


def save_message(call_id: int | None, queue_id: int | None, name: str, callback_number: str, message: str) -> None:
    if call_id is None:
        return
    with SessionLocal() as db:
        db.add(Message(call_id=call_id, queue_id=queue_id, name=name, callback_number=callback_number, message=message))
        db.commit()


def knowledge_message(results: list[tuple[str, float]], min_score: float) -> str:
    relevant = [text for text, score in results if score >= min_score]
    if relevant:
        return "BASE DE CONHECIMENTO (trechos relevantes para a última fala):\n\n" + "\n---\n".join(relevant)
    return ("BASE DE CONHECIMENTO: nada relevante para a última fala. Se o cliente perguntou algo sobre a empresa, "
            "não invente: diga que vai passar para um atendente e chame transfer_to_human com reason='no_answer'.")


class PhoneAgent(Agent):
    """ctx/call_id = None roda o agente fora de uma chamada (evals): mesmas regras e ferramentas, sem sala nem banco."""

    def __init__(self, ctx: JobContext | None, target: Target, call_id: int | None, caller: str, transcript: list,
                 knowledge: str | None = None):
        """knowledge = base inteira (pequena) no prompt, sem busca por fala; None = busca."""
        if knowledge is not None:
            rule = KNOWLEDGE_RULE_INLINE
        else:
            rule = KNOWLEDGE_RULE_REALTIME if isinstance(self, RealtimePhoneAgent) else KNOWLEDGE_RULE_PIPELINE
        instructions = PLATFORM_RULES.format(knowledge_rule=rule) + (target.agent.rules_md or "")
        if knowledge is not None:
            instructions += "\n\nBASE DE CONHECIMENTO:\n\n" + (knowledge or "(vazia)")
        super().__init__(instructions=instructions)
        self.knowledge = knowledge
        self.ctx = ctx
        self.target = target
        self.call_id = call_id
        self.caller = caller
        self.transcript = transcript
        self.background: BackgroundAudioPlayer | None = None
        self.handoff_task: asyncio.Task | None = None

    async def on_user_turn_completed(self, turn_ctx: ChatContext, new_message: ChatMessage) -> None:
        """Busca na base antes do LLM: evita uma ida e volta inteira ao LLM só para decidir buscar (~1,4 s)."""
        query = new_message.text_content
        if not query or self.knowledge is not None:
            return
        try:
            results = await rag.search(self.target.agent, query)
        except Exception:
            logger.exception("falha na busca de conhecimento")
            results = []
        turn_ctx.add_message(role="system", content=knowledge_message(results, self.target.agent.rag_min_score))

    @function_tool
    async def transfer_to_human(
        self,
        context: RunContext,
        reason: Literal["customer_request", "out_of_scope", "no_answer", "provider_failure"],
        summary: str,
    ) -> str:
        """Transfere a ligação para um atendente humano.

        Args:
            reason: customer_request (cliente pediu), out_of_scope (fora do escopo), no_answer (sem resposta na base)
            summary: resumo para o atendente em 2 a 4 frases: quem é o cliente, o que ele quer e o que já foi dito
        """
        assert reason in REASONS
        instruction = await self.start_transfer(reason, summary)
        if instruction is None:
            raise StopResponse()  # o aviso de transferência já foi falado; o LLM não responde
        return instruction

    @function_tool
    async def take_message(self, context: RunContext, name: str, callback_number: str, message: str) -> str:
        """Registra um recado para a equipe retornar a ligação. Use quando não for possível transferir.

        Args:
            name: nome do cliente
            callback_number: telefone para retorno; se o cliente disser que é o mesmo, use "mesmo número"
            message: o recado, com o assunto e o que o cliente precisa
        """
        number = self.caller if callback_number.strip().lower() in ("mesmo número", "mesmo numero", "") else callback_number
        queue_id = self.target.queue.id if self.target.queue else None
        await asyncio.to_thread(save_message, self.call_id, queue_id, name, number, message)
        return "Recado registrado. Confirme ao cliente que a equipe vai retornar e pergunte se pode ajudar em algo mais."

    @function_tool
    async def end_call(self, context: RunContext) -> None:
        """Encerra a ligação. Use só depois de se despedir do cliente."""
        if self.ctx is None:
            return
        await context.wait_for_playout()
        await self.ctx.delete_room()

    async def start_transfer(self, reason: str, summary: str) -> str | None:
        """Decide entre transferir e pegar recado. Devolve a instrução para o LLM, ou None se já anunciou a transferência."""
        if self.handoff_task:
            return "A transferência já está em andamento. Peça ao cliente para aguardar na linha."
        queue = self.target.queue
        decision = decide(queue_id=queue.id if queue else None, hours=queue.hours if queue else None,
                          holidays=queue.holidays if queue else None, at=now())
        await asyncio.to_thread(update_call, self.call_id, transfer_reason=reason, summary=summary)
        if decision.action == "take_message":
            return (f"Não dá para transferir agora ({decision.reason}). Explique isso ao cliente com gentileza e ofereça "
                    "deixar um recado: peça o nome, um telefone para retorno e a mensagem, depois chame take_message.")
        if self.ctx is None:  # evals: sem sala, só registra a decisão
            return "Transferência iniciada. Diga ao cliente que vai transferir para um atendente e que ele aguarde."
        await asyncio.to_thread(update_call, self.call_id, status="waiting_human", waiting_since=now(),
                                transcript=list(self.transcript))
        self.session.input.set_audio_enabled(False)  # o agente não responde mais; o cliente só aguarda
        announcement = self.session.say(TRANSFER_ANNOUNCEMENT, allow_interruptions=False)
        self.handoff_task = asyncio.create_task(self._wait_for_attendant(announcement))
        return None

    async def _wait_for_attendant(self, announcement: SpeechHandle) -> None:
        """Música de espera até um atendente entrar na sala. Ao entrar, o agente sai e os dois conversam direto."""
        session = self.session
        await announcement.wait_for_playout()
        hold = self.background.play(BuiltinAudioClip.HOLD_MUSIC, loop=True) if self.background else None
        joined = asyncio.Event()

        def on_join(p: rtc.RemoteParticipant) -> None:
            if p.identity.startswith(ATTENDANT_PREFIX):
                joined.set()

        self.ctx.room.on("participant_connected", on_join)
        if any(i.startswith(ATTENDANT_PREFIX) for i in self.ctx.room.remote_participants):
            joined.set()
        timeout = self.target.queue.wait_timeout_s if self.target.queue else 120
        try:
            await asyncio.wait_for(joined.wait(), timeout)
        except asyncio.TimeoutError:
            if not await asyncio.to_thread(cancel_wait, self.call_id):
                await asyncio.wait_for(joined.wait(), 30)  # aceitou no último instante; aguarda entrar
        finally:
            self.ctx.room.off("participant_connected", on_join)
            if hold:
                hold.stop()

        if joined.is_set():
            logger.info("atendente entrou; agente saindo da chamada %s", self.call_id)
            self.ctx.shutdown("transferido para humano")
            return
        self.handoff_task = None
        session.input.set_audio_enabled(True)
        session.generate_reply(instructions=(
            "Nenhum atendente atendeu. Peça desculpas pela espera e ofereça deixar um recado: "
            "nome, telefone para retorno e mensagem; depois chame take_message."))


def build_session(profile: AgentProfile, vad) -> AgentSession:
    """pipeline (STT -> LLM -> TTS) ou realtime (speech-to-speech). No realtime, o TTS só fala os textos fixos."""
    tts = registry.build_tts(profile.tts or DEFAULT_TTS, profile.language)
    if profile.voice_mode == "realtime" and profile.realtime:
        try:
            return AgentSession(llm=registry.build_realtime(profile.realtime, profile.language), tts=tts, vad=vad)
        except Exception:
            # shortcut: só cobre falha ao montar o modelo; queda da conexão realtime no meio da chamada não troca de modo.
            logger.exception("realtime indisponível para o agente %s; usando pipeline", profile.id)
    return AgentSession(
        stt=registry.build_stt(profile.stt or DEFAULT_STT, profile.language, vad=vad),
        llm=registry.build_llm(profile.llm or DEFAULT_LLM, profile.language),
        tts=tts,
        vad=vad,
        # Detector de fim de turno do LiveKit Cloud; cai para o modelo local se a nuvem falhar.
        turn_handling={"turn_detection": inference.TurnDetector()},
    )


class RealtimePhoneAgent(PhoneAgent):
    """Modo speech-to-speech: busca na base como ferramenta (a fala do cliente ainda não foi transcrita quando o modelo
    começa a responder)."""

    async def on_user_turn_completed(self, turn_ctx: ChatContext, new_message: ChatMessage) -> None:
        return

    @function_tool
    async def search_knowledge(self, context: RunContext, query: str) -> str:
        """Busca na base de conhecimento da empresa. Use antes de responder qualquer pergunta sobre a empresa.

        Args:
            query: a dúvida do cliente, escrita como uma busca curta e objetiva
        """
        try:
            results = await rag.search(self.target.agent, query)
        except Exception:
            logger.exception("falha na busca de conhecimento")
            results = []
        return knowledge_message(results, self.target.agent.rag_min_score)


server = AgentServer()


def prewarm(proc: JobProcess) -> None:
    install_log_redaction()
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session(agent_name="voxbr")
async def entrypoint(ctx: JobContext) -> None:
    meta = json.loads(ctx.job.metadata or "{}")
    caller = await ctx.wait_for_participant()
    did = caller.attributes.get("sip.trunkPhoneNumber", "")  # vazio em chamadas pelo navegador
    caller_number = caller.attributes.get("sip.phoneNumber", "")
    target = await asyncio.to_thread(resolve_target, did, meta)
    call_id = await asyncio.to_thread(create_call, ctx.room.name, target, caller_number)
    profile = target.agent
    logger.info("chamada %s: did=%s agente=%s modo=%s", call_id, did or "web", profile.name, target.mode)

    session = build_session(profile, ctx.proc.userdata["vad"])
    profile.embedding = profile.embedding or DEFAULT_EMBEDDING
    transcript: list[dict] = []

    @session.on("conversation_item_added")
    def _on_item(ev: ConversationItemAddedEvent) -> None:
        text = getattr(ev.item, "text_content", None)
        if text:
            transcript.append({"role": ev.item.role, "text": text, "at": now().isoformat()})

    @session.on("metrics_collected")
    def _on_metrics(ev: MetricsCollectedEvent) -> None:
        metrics.log_metrics(ev.metrics, logger=logger)

    async def _finish(_reason: str = "") -> None:
        usage = cost_usd([u.model_dump() for u in session.usage.model_usage])
        await asyncio.to_thread(finish_call, call_id, transcript, usage)

    ctx.add_shutdown_callback(_finish)

    knowledge = rag.inline_knowledge(target.agent)
    realtime = isinstance(session.llm, llm.RealtimeModel)
    agent_cls = RealtimePhoneAgent if realtime and knowledge is None else PhoneAgent
    agent = agent_cls(ctx, target, call_id, caller_number, transcript, knowledge)
    await session.start(agent, room=ctx.room)
    agent.background = BackgroundAudioPlayer()
    await agent.background.start(room=ctx.room, agent_session=session)

    # Aviso LGPD antes de qualquer conversa; não pode ser interrompido. O microfone fica mudo para o agente
    # porque no modo realtime a detecção de turno é do servidor e ignora allow_interruptions=False.
    session.input.set_audio_enabled(False)
    await session.say(profile.recording_notice, allow_interruptions=False)
    session.input.set_audio_enabled(True)
    if target.mode == "human_direct":
        instruction = await agent.start_transfer("customer_request", "Ligação direta para atendimento humano.")
        if instruction:  # fila fechada: a IA oferece recado
            session.generate_reply(instructions=instruction)
    else:
        session.say(profile.greeting)


if __name__ == "__main__":
    cli.run_app(server)
