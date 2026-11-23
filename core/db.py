"""Modelo de dados. Tudo que o operador configura pelo painel vive aqui (números, agentes IA, filas, atendentes)."""

import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    create_engine,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://voxbr:voxbr@127.0.0.1:5435/voxbr")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


queue_members = Table(
    "queue_members",
    Base.metadata,
    Column("queue_id", ForeignKey("queues.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20), default="attendant")  # admin | attendant
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    queues: Mapped[list["Queue"]] = relationship(secondary=queue_members, back_populates="members")


class Queue(Base):
    """Fila humana: destino do transbordo e dos números em modo 'human_direct'."""

    __tablename__ = "queues"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    # {"tz": "America/Sao_Paulo", "days": {"mon": [["08:00", "18:00"]], ...}}; dia ausente = fechado.
    hours: Mapped[dict] = mapped_column(JSON, default=dict)
    holidays: Mapped[list] = mapped_column(JSON, default=list)  # ["2026-12-25", ...]
    wait_timeout_s: Mapped[int] = mapped_column(Integer, default=120)
    members: Mapped[list[User]] = relationship(secondary=queue_members, back_populates="queues")


class AgentProfile(Base):
    """Agente de IA. `rules_md` é o "rules.md" do agente, editado no painel."""

    __tablename__ = "agents"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    rules_md: Mapped[str] = mapped_column(Text, default="")
    greeting: Mapped[str] = mapped_column(Text, default="Olá! Em que posso ajudar?")
    recording_notice: Mapped[str] = mapped_column(
        Text,
        default="Esta ligação pode ser gravada para fins de qualidade e segurança. "
        "Você está falando com um assistente virtual.",
    )
    language: Mapped[str] = mapped_column(String(10), default="pt")
    # Listas de ProviderSpec ({vendor, model, options}); mais de um item = fallback na ordem.
    stt: Mapped[list] = mapped_column(JSON, default=list)
    llm: Mapped[list] = mapped_column(JSON, default=list)
    tts: Mapped[list] = mapped_column(JSON, default=list)
    # pipeline = STT -> LLM -> TTS; realtime = modelo speech-to-speech (o TTS ainda fala os textos fixos, ex.: aviso LGPD)
    voice_mode: Mapped[str] = mapped_column(String(20), default="pipeline")
    realtime: Mapped[list] = mapped_column(JSON, default=list)
    embedding: Mapped[dict] = mapped_column(JSON, default=dict)
    rag_min_score: Mapped[float] = mapped_column(Float, default=0.35)


class PhoneNumber(Base):
    __tablename__ = "numbers"
    id: Mapped[int] = mapped_column(primary_key=True)
    did: Mapped[str] = mapped_column(String(30), unique=True)  # E.164
    label: Mapped[str] = mapped_column(String(200), default="")
    mode: Mapped[str] = mapped_column(String(20), default="ai")  # ai | human_direct
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"))
    queue_id: Mapped[int | None] = mapped_column(ForeignKey("queues.id", ondelete="SET NULL"))
    retention_days: Mapped[int] = mapped_column(Integer, default=90)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    agent: Mapped[AgentProfile | None] = relationship()
    queue: Mapped[Queue | None] = relationship()


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(String(10))  # file | url
    content: Mapped[str] = mapped_column(Text, default="")  # texto extraído; permite reindexar ao trocar o embedding
    status: Mapped[str] = mapped_column(String(20), default="processing")  # processing | ready | error
    error: Mapped[str] = mapped_column(Text, default="")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text)
    embedding_model: Mapped[str] = mapped_column(String(100))
    # shortcut: vetor sem dimensão fixa = busca exata (sem índice HNSW); ok até ~100 mil chunks por agente.
    embedding = mapped_column(Vector())


class Call(Base):
    __tablename__ = "calls"
    id: Mapped[int] = mapped_column(primary_key=True)
    room: Mapped[str] = mapped_column(String(200), index=True)
    did: Mapped[str] = mapped_column(String(30), default="")  # vazio = teste pelo navegador
    caller: Mapped[str] = mapped_column(String(30), default="")
    number_id: Mapped[int | None] = mapped_column(ForeignKey("numbers.id", ondelete="SET NULL"))
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"))
    queue_id: Mapped[int | None] = mapped_column(ForeignKey("queues.id", ondelete="SET NULL"))
    attendant_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # ai | waiting_human | with_human | ended
    status: Mapped[str] = mapped_column(String(20), default="ai")
    transfer_reason: Mapped[str] = mapped_column(String(50), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    transcript: Mapped[list] = mapped_column(JSON, default=list)  # [{role, text, at}]
    usage: Mapped[list] = mapped_column(JSON, default=list)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    waiting_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # entrou na fila humana
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    number: Mapped[PhoneNumber | None] = relationship()
    agent: Mapped[AgentProfile | None] = relationship()
    queue: Mapped[Queue | None] = relationship()
    attendant: Mapped[User | None] = relationship()


class Message(Base):
    """Recado deixado fora do horário ou quando nenhum atendente atendeu (pedido de callback)."""

    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int | None] = mapped_column(ForeignKey("calls.id", ondelete="SET NULL"))
    queue_id: Mapped[int | None] = mapped_column(ForeignKey("queues.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(200), default="")
    callback_number: Mapped[str] = mapped_column(String(30), default="")
    message: Mapped[str] = mapped_column(Text, default="")
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    queue: Mapped[Queue | None] = relationship()


def init_db() -> None:
    # shortcut: create_all sem migrações; trocar por Alembic antes do primeiro deploy com dados reais.
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
    with engine.begin() as conn:  # colunas adicionadas depois da primeira versão
        conn.execute(text("ALTER TABLE calls ADD COLUMN IF NOT EXISTS waiting_since TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE agents ADD COLUMN IF NOT EXISTS voice_mode VARCHAR(20) DEFAULT 'pipeline'"))
        conn.execute(text("ALTER TABLE agents ADD COLUMN IF NOT EXISTS realtime JSON DEFAULT '[]'"))
