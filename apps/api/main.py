"""API do painel do operador e do console do atendente."""

import json
import logging
import os
from datetime import datetime

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response, UploadFile
from livekit import api as lkapi
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from core import rag
from core.auth import hash_password, issue_session, read_session, verify_password
from core.config import DEFAULT_EMBEDDING, DEFAULT_LLM, DEFAULT_STT, DEFAULT_TTS, ProviderSpec, normalize_did
from core.db import AgentProfile, Call, Document, Message, PhoneNumber, Queue, SessionLocal, User, init_db, now
from core.handoff import DAYS, REASONS
from core.lgpd import install_log_redaction
from core.providers.registry import CATALOG

load_dotenv()
install_log_redaction()
logger = logging.getLogger("voxbr.api")

COOKIE = "voxbr_session"
AGENT_NAME = "voxbr"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

app = FastAPI(title="voxbr")


# ---------- infraestrutura ----------


def get_db():
    with SessionLocal() as db:
        yield db


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = read_session(request.cookies.get(COOKIE, ""))
    user = db.get(User, user_id) if user_id else None
    if not user or not user.active:
        raise HTTPException(401, "não autenticado")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "apenas administradores")
    return user


def get_or_404(db: Session, model, id_: int):
    obj = db.get(model, id_)
    if obj is None:
        raise HTTPException(404, "não encontrado")
    return obj


def livekit_token(identity: str, name: str, room: str, dispatch_metadata: dict | None = None) -> str:
    token = (
        lkapi.AccessToken(os.environ["LIVEKIT_API_KEY"], os.environ["LIVEKIT_API_SECRET"])
        .with_identity(identity)
        .with_name(name)
        .with_grants(lkapi.VideoGrants(room_join=True, room=room))
    )
    if dispatch_metadata is not None:
        token = token.with_room_config(
            lkapi.RoomConfiguration(
                agents=[lkapi.RoomAgentDispatch(agent_name=AGENT_NAME, metadata=json.dumps(dispatch_metadata))]
            )
        )
    return token.to_jwt()


DEFAULT_RULES = """# Regras do agente

## Quem você é
Atendente virtual da empresa. Fale sempre em português do Brasil.

## O que você resolve
- (liste aqui os assuntos que o agente pode atender)

## O que você NÃO faz
- Não negocia valores nem dá descontos.
- Não promete prazos que não estejam na base de conhecimento.

## Quando transferir para um humano
- O cliente pede para falar com uma pessoa.
- O assunto está fora da lista acima.
- A base de conhecimento não tem a resposta.
"""


@app.on_event("startup")
def bootstrap() -> None:
    init_db()
    with SessionLocal() as db:
        if not db.scalar(select(func.count(User.id))):
            email, password = os.environ.get("ADMIN_EMAIL"), os.environ.get("ADMIN_PASSWORD")
            if email and password:
                db.add(User(email=email.lower(), name="Administrador", password_hash=hash_password(password), role="admin"))
                logger.info("administrador inicial criado: %s", email)
            else:
                logger.warning("nenhum usuário: defina ADMIN_EMAIL e ADMIN_PASSWORD no .env")
        if not db.scalar(select(func.count(AgentProfile.id))):
            db.add(
                AgentProfile(
                    name="Atendimento padrão",
                    rules_md=DEFAULT_RULES,
                    stt=DEFAULT_STT,
                    llm=DEFAULT_LLM,
                    tts=DEFAULT_TTS,
                    embedding=DEFAULT_EMBEDDING,
                )
            )
        db.commit()


# ---------- auth ----------


class LoginIn(BaseModel):
    email: str
    password: str


def user_out(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role, "active": u.active,
            "queue_ids": [q.id for q in u.queues]}


@app.post("/api/auth/login")
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if not user or not user.active or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "e-mail ou senha inválidos")
    response.set_cookie(
        COOKIE, issue_session(user.id), httponly=True, samesite="lax",
        secure=os.environ.get("COOKIE_SECURE", "false") == "true", max_age=12 * 3600,
    )
    return user_out(user)


@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE)
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: User = Depends(current_user)):
    return user_out(user)


@app.get("/api/catalog")
def catalog(_: User = Depends(current_user)):
    return {"providers": CATALOG, "reasons": REASONS, "days": DAYS}


# ---------- agentes de IA ----------


class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    rules_md: str = ""
    greeting: str = Field(min_length=1)
    recording_notice: str = Field(min_length=1)
    language: str = "pt"
    stt: list[ProviderSpec] = Field(min_length=1)
    llm: list[ProviderSpec] = Field(min_length=1)
    tts: list[ProviderSpec] = Field(min_length=1)
    voice_mode: str = Field("pipeline", pattern="^(pipeline|realtime)$")
    realtime: list[ProviderSpec] = []
    embedding: ProviderSpec
    rag_min_score: float = Field(0.35, ge=0, le=1)


def agent_out(a: AgentProfile, db: Session) -> dict:
    docs = db.scalar(select(func.count(Document.id)).where(Document.agent_id == a.id))
    return {
        "id": a.id, "name": a.name, "rules_md": a.rules_md, "greeting": a.greeting,
        "recording_notice": a.recording_notice, "language": a.language, "stt": a.stt, "llm": a.llm,
        "tts": a.tts, "voice_mode": a.voice_mode, "realtime": a.realtime, "embedding": a.embedding, "rag_min_score": a.rag_min_score, "document_count": docs,
    }


@app.get("/api/agents")
def list_agents(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return [agent_out(a, db) for a in db.scalars(select(AgentProfile).order_by(AgentProfile.name))]


def check_agent(body: AgentIn) -> AgentIn:
    if body.voice_mode == "realtime" and not body.realtime:
        raise HTTPException(422, "modo realtime precisa de um modelo realtime")
    return body


@app.post("/api/agents", status_code=201)
def create_agent(body: AgentIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    agent = AgentProfile(**check_agent(body).model_dump())
    db.add(agent)
    db.commit()
    return agent_out(agent, db)


@app.get("/api/agents/{agent_id}")
def get_agent(agent_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return agent_out(get_or_404(db, AgentProfile, agent_id), db)


@app.put("/api/agents/{agent_id}")
def update_agent(agent_id: int, body: AgentIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    agent = get_or_404(db, AgentProfile, agent_id)
    for k, v in check_agent(body).model_dump().items():
        setattr(agent, k, v)
    db.commit()
    out = agent_out(agent, db)
    out["stale_chunks"] = rag.model_mismatch_count(agent)  # >0 = trocou o embedding; reindexar
    return out


@app.delete("/api/agents/{agent_id}", status_code=204)
def delete_agent(agent_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if db.scalar(select(func.count(PhoneNumber.id)).where(PhoneNumber.agent_id == agent_id)):
        raise HTTPException(409, "agente em uso por um número; troque o agente do número antes")
    db.delete(get_or_404(db, AgentProfile, agent_id))
    db.commit()


# ---------- base de conhecimento ----------


def doc_out(d: Document) -> dict:
    return {"id": d.id, "name": d.name, "source": d.source, "status": d.status, "error": d.error,
            "chunk_count": d.chunk_count, "created_at": d.created_at}


@app.get("/api/agents/{agent_id}/documents")
def list_documents(agent_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    docs = db.scalars(select(Document).where(Document.agent_id == agent_id).order_by(Document.created_at.desc()))
    return [doc_out(d) for d in docs]


@app.post("/api/agents/{agent_id}/documents", status_code=201)
async def upload_document(agent_id: int, file: UploadFile, tasks: BackgroundTasks,
                          db: Session = Depends(get_db), _: User = Depends(require_admin)):
    get_or_404(db, AgentProfile, agent_id)
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "arquivo maior que 20 MB")
    try:
        content = rag.extract_text(file.filename or "", data)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception:
        raise HTTPException(422, "não foi possível ler o arquivo")
    doc = Document(agent_id=agent_id, name=file.filename or "arquivo", source="file", content=content)
    db.add(doc)
    db.commit()
    tasks.add_task(rag.ingest, doc.id, content)
    return doc_out(doc)


class UrlIn(BaseModel):
    url: str


@app.post("/api/agents/{agent_id}/documents/url", status_code=201)
async def add_url(agent_id: int, body: UrlIn, tasks: BackgroundTasks,
                  db: Session = Depends(get_db), _: User = Depends(require_admin)):
    get_or_404(db, AgentProfile, agent_id)
    try:
        content = await rag.fetch_url(body.url.strip())
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception:
        raise HTTPException(422, "não foi possível baixar a página")
    doc = Document(agent_id=agent_id, name=body.url.strip(), source="url", content=content)
    db.add(doc)
    db.commit()
    tasks.add_task(rag.ingest, doc.id, content)
    return doc_out(doc)


@app.post("/api/agents/{agent_id}/reindex")
def reindex(agent_id: int, tasks: BackgroundTasks, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    docs = db.scalars(select(Document).where(Document.agent_id == agent_id)).all()
    for d in docs:
        d.status = "processing"
        tasks.add_task(rag.ingest, d.id, d.content)
    db.commit()
    return {"queued": len(docs)}


@app.delete("/api/documents/{doc_id}", status_code=204)
def delete_document(doc_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    db.delete(get_or_404(db, Document, doc_id))
    db.commit()


class SearchIn(BaseModel):
    query: str = Field(min_length=1)


@app.post("/api/agents/{agent_id}/search")
async def search_knowledge(agent_id: int, body: SearchIn, db: Session = Depends(get_db),
                           _: User = Depends(require_admin)):
    """Teste da busca no painel: mostra o que o agente encontraria e o score de cada trecho."""
    agent = get_or_404(db, AgentProfile, agent_id)
    results = await rag.search(agent, body.query)
    return [{"text": t, "score": s, "relevant": s >= agent.rag_min_score} for t, s in results]


# ---------- filas e usuários ----------


class QueueIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    hours: dict = {}
    holidays: list[str] = []
    wait_timeout_s: int = Field(120, ge=15, le=1800)
    member_ids: list[int] = []


def queue_out(q: Queue) -> dict:
    return {"id": q.id, "name": q.name, "hours": q.hours, "holidays": q.holidays,
            "wait_timeout_s": q.wait_timeout_s, "member_ids": [m.id for m in q.members]}


def validate_hours(hours: dict) -> dict:
    for day, ranges in (hours.get("days") or {}).items():
        if day not in DAYS:
            raise HTTPException(422, f"dia inválido: {day}")
        for start, end in ranges:
            try:
                if datetime.strptime(start, "%H:%M") >= datetime.strptime(end, "%H:%M"):
                    raise ValueError
            except ValueError:
                raise HTTPException(422, f"horário inválido em {day}: {start}-{end}")
    return hours


def save_queue(q: Queue, body: QueueIn, db: Session) -> Queue:
    q.name, q.hours, q.holidays, q.wait_timeout_s = body.name, validate_hours(body.hours), body.holidays, body.wait_timeout_s
    q.members = list(db.scalars(select(User).where(User.id.in_(body.member_ids))))
    db.commit()
    return q


@app.get("/api/queues")
def list_queues(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return [queue_out(q) for q in db.scalars(select(Queue).order_by(Queue.name))]


@app.post("/api/queues", status_code=201)
def create_queue(body: QueueIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    q = Queue()
    db.add(q)
    return queue_out(save_queue(q, body, db))


@app.put("/api/queues/{queue_id}")
def update_queue(queue_id: int, body: QueueIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return queue_out(save_queue(get_or_404(db, Queue, queue_id), body, db))


@app.delete("/api/queues/{queue_id}", status_code=204)
def delete_queue(queue_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    db.delete(get_or_404(db, Queue, queue_id))
    db.commit()


class UserIn(BaseModel):
    email: str = Field(min_length=3)
    name: str = Field(min_length=1)
    role: str = Field("attendant", pattern="^(admin|attendant)$")
    active: bool = True
    password: str | None = Field(None, min_length=8)
    queue_ids: list[int] = []


@app.get("/api/users")
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return [user_out(u) for u in db.scalars(select(User).order_by(User.name))]


def save_user(u: User, body: UserIn, db: Session) -> User:
    u.email, u.name, u.role, u.active = body.email.strip().lower(), body.name, body.role, body.active
    if body.password:
        u.password_hash = hash_password(body.password)
    with db.no_autoflush:  # senão o autoflush da consulta estoura o IntegrityError fora do try (500 em vez de 409)
        u.queues = list(db.scalars(select(Queue).where(Queue.id.in_(body.queue_ids))))
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(409, "e-mail já cadastrado")
    return u


@app.post("/api/users", status_code=201)
def create_user(body: UserIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if not body.password:
        raise HTTPException(422, "senha obrigatória (mínimo 8 caracteres)")
    u = User()
    db.add(u)
    return user_out(save_user(u, body, db))


@app.put("/api/users/{user_id}")
def update_user(user_id: int, body: UserIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    u = get_or_404(db, User, user_id)
    if u.id == admin.id and (body.role != "admin" or not body.active):
        raise HTTPException(409, "você não pode remover o próprio acesso de administrador")
    return user_out(save_user(u, body, db))


@app.delete("/api/users/{user_id}", status_code=204)
def delete_user(user_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if user_id == admin.id:
        raise HTTPException(409, "você não pode excluir a si mesmo")
    db.delete(get_or_404(db, User, user_id))
    db.commit()


# ---------- números ----------


class NumberIn(BaseModel):
    did: str = Field(min_length=8)
    label: str = ""
    mode: str = Field("ai", pattern="^(ai|human_direct)$")
    agent_id: int | None = None
    queue_id: int | None = None
    retention_days: int = Field(90, ge=1, le=3650)
    active: bool = True


def number_out(n: PhoneNumber) -> dict:
    return {"id": n.id, "did": n.did, "label": n.label, "mode": n.mode, "agent_id": n.agent_id,
            "queue_id": n.queue_id, "retention_days": n.retention_days, "active": n.active,
            "agent_name": n.agent.name if n.agent else None, "queue_name": n.queue.name if n.queue else None}


def save_number(n: PhoneNumber, body: NumberIn, db: Session) -> PhoneNumber:
    if body.mode == "ai" and not body.agent_id:
        raise HTTPException(422, "número em modo IA precisa de um agente")
    if body.mode == "human_direct" and not body.queue_id:
        raise HTTPException(422, "número direto para operador precisa de uma fila")
    for k, v in body.model_dump().items():
        setattr(n, k, v)
    n.did = normalize_did(body.did)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(409, "número já cadastrado")
    db.refresh(n)
    return n


@app.get("/api/numbers")
def list_numbers(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return [number_out(n) for n in db.scalars(select(PhoneNumber).order_by(PhoneNumber.did))]


@app.post("/api/numbers", status_code=201)
def create_number(body: NumberIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    n = PhoneNumber()
    db.add(n)
    return number_out(save_number(n, body, db))


@app.put("/api/numbers/{number_id}")
def update_number(number_id: int, body: NumberIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return number_out(save_number(get_or_404(db, PhoneNumber, number_id), body, db))


@app.delete("/api/numbers/{number_id}", status_code=204)
def delete_number(number_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    db.delete(get_or_404(db, PhoneNumber, number_id))
    db.commit()


class TestCallIn(BaseModel):
    number_id: int | None = None
    agent_id: int | None = None


@app.post("/api/test-call")
def test_call(body: TestCallIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Ligação de teste pelo navegador, como se fosse para o número (ou direto para um agente)."""
    if body.number_id:
        get_or_404(db, PhoneNumber, body.number_id)
    elif body.agent_id:
        get_or_404(db, AgentProfile, body.agent_id)
    else:
        raise HTTPException(422, "informe number_id ou agent_id")
    room = f"teste-{int(now().timestamp() * 1000)}"
    meta = {"number_id": body.number_id} if body.number_id else {"agent_id": body.agent_id}
    token = livekit_token(f"cliente-teste-{user.id}", "Cliente (teste)", room, dispatch_metadata=meta)
    return {"server_url": os.environ["LIVEKIT_URL"], "token": token, "room": room}


# ---------- chamadas e recados ----------


def call_out(c: Call, full: bool = False) -> dict:
    out = {
        "id": c.id, "room": c.room, "did": c.did, "caller": c.caller, "status": c.status,
        "transfer_reason": c.transfer_reason, "summary": c.summary, "cost_usd": c.cost_usd,
        "started_at": c.started_at, "ended_at": c.ended_at, "waiting_since": c.waiting_since,
        "number_label": c.number.label if c.number else "", "agent_name": c.agent.name if c.agent else "",
        "queue_name": c.queue.name if c.queue else "", "attendant_name": c.attendant.name if c.attendant else "",
    }
    if full:
        out |= {"transcript": c.transcript, "usage": c.usage}
    return out


@app.get("/api/calls")
def list_calls(limit: int = 100, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    calls = db.scalars(select(Call).order_by(Call.started_at.desc()).limit(min(limit, 500)))
    return [call_out(c) for c in calls]


@app.get("/api/calls/{call_id}")
def get_call(call_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    call = get_or_404(db, Call, call_id)
    if user.role != "admin" and call.attendant_id != user.id and call.queue_id not in {q.id for q in user.queues}:
        raise HTTPException(403, "chamada de outra fila")
    return call_out(call, full=True)


def visible_queue_ids(user: User, db: Session) -> list[int]:
    if user.role == "admin":
        return list(db.scalars(select(Queue.id)))
    return [q.id for q in user.queues]


@app.get("/api/messages")
def list_messages(db: Session = Depends(get_db), user: User = Depends(current_user)):
    query = select(Message).order_by(Message.done, Message.created_at.desc()).limit(200)
    if user.role != "admin":
        query = query.where(Message.queue_id.in_(visible_queue_ids(user, db)))
    return [
        {"id": m.id, "call_id": m.call_id, "name": m.name, "callback_number": m.callback_number,
         "message": m.message, "done": m.done, "created_at": m.created_at,
         "queue_name": m.queue.name if m.queue else ""}
        for m in db.scalars(query)
    ]


class MessagePatch(BaseModel):
    done: bool


@app.patch("/api/messages/{message_id}")
def patch_message(message_id: int, body: MessagePatch, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    msg = get_or_404(db, Message, message_id)
    if user.role != "admin" and msg.queue_id not in visible_queue_ids(user, db):
        raise HTTPException(403, "recado de outra fila")
    msg.done = body.done
    db.commit()
    return {"ok": True}


# ---------- console do atendente ----------


@app.get("/api/console")
def console_state(db: Session = Depends(get_db), user: User = Depends(current_user)):
    queues = visible_queue_ids(user, db)
    waiting = db.scalars(
        select(Call).where(Call.status == "waiting_human", Call.queue_id.in_(queues)).order_by(Call.waiting_since, Call.started_at)
    )
    mine = db.scalars(select(Call).where(Call.status == "with_human", Call.attendant_id == user.id))
    return {"waiting": [call_out(c, full=True) for c in waiting], "active": [call_out(c, full=True) for c in mine]}


@app.post("/api/console/calls/{call_id}/accept")
def accept_call(call_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    call = get_or_404(db, Call, call_id)
    if call.queue_id not in visible_queue_ids(user, db):
        raise HTTPException(403, "chamada de outra fila")
    # UPDATE condicional: se dois atendentes clicarem juntos, só um leva a chamada.
    taken = db.execute(
        update(Call).where(Call.id == call_id, Call.status == "waiting_human")
        .values(status="with_human", attendant_id=user.id)
    ).rowcount
    db.commit()
    rejoin = call.status == "with_human" and call.attendant_id == user.id  # recarregou a página no meio da chamada
    if not taken and not rejoin:
        raise HTTPException(409, "chamada já atendida ou encerrada")
    token = livekit_token(f"atendente-{user.id}", user.name, call.room)
    return {"server_url": os.environ["LIVEKIT_URL"], "token": token, "room": call.room}


@app.post("/api/console/calls/{call_id}/hangup")
async def hangup_call(call_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    call = get_or_404(db, Call, call_id)
    if user.role != "admin" and call.attendant_id != user.id:
        raise HTTPException(403, "chamada de outro atendente")
    async with lkapi.LiveKitAPI() as lk:
        try:
            await lk.room.delete_room(lkapi.DeleteRoomRequest(room=call.room))
        except lkapi.TwirpError as e:
            if e.code != "not_found":
                raise
    call.status, call.ended_at = "ended", call.ended_at or now()
    db.commit()
    return {"ok": True}
