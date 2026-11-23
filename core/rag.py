"""RAG por agente: extração (PDF, DOCX, TXT, URL), chunking, indexação em pgvector e busca."""

import asyncio
import io
import ipaddress
import logging
import re
import socket
from urllib.parse import urlparse

import httpx
from sqlalchemy import delete, select, text

from core.config import DEFAULT_EMBEDDING
from core.db import AgentProfile, Chunk, Document, SessionLocal
from core.embeddings import build_embedding, embedding_model_id

logger = logging.getLogger("voxbr.rag")

CHUNK_CHARS = 1200
OVERLAP_CHARS = 200


def extract_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
    if name.endswith(".docx"):
        from docx import Document as Docx

        return "\n".join(p.text for p in Docx(io.BytesIO(data)).paragraphs)
    if name.endswith((".txt", ".md")):
        return data.decode("utf-8", errors="replace")
    raise ValueError("formato não suportado (use PDF, DOCX, TXT ou MD)")


def html_to_text(html: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    return soup.get_text("\n")


async def _assert_public_host(url: str) -> None:
    """Bloqueia URLs que apontam para a rede interna (SSRF): banco, metadados da nuvem, localhost."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("URL precisa começar com http:// ou https://")
    infos = await asyncio.to_thread(socket.getaddrinfo, parsed.hostname, None)
    for info in infos:
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise ValueError("URL aponta para endereço interno; não permitido")


async def fetch_url(url: str) -> str:
    await _assert_public_host(url)
    # shortcut: redirecionamentos não são revalidados contra a rede interna; revalidar antes de abrir o painel a terceiros.
    async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
        res = await client.get(url, headers={"User-Agent": "voxbr-rag/0.1"})
        res.raise_for_status()
    return html_to_text(res.text)


def chunk_text(content: str, size: int = CHUNK_CHARS, overlap: int = OVERLAP_CHARS) -> list[str]:
    """Junta parágrafos até ~size caracteres; parágrafo maior que size é fatiado com sobreposição."""
    paragraphs = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n|\n", content)]
    chunks: list[str] = []
    current = ""
    has_body = False  # o trecho atual tem texto além de títulos
    for p in filter(None, paragraphs):
        if p.startswith("#"):
            if has_body:  # título de seção começa trecho novo: buscas mais precisas
                chunks.append(current)
                current, has_body = "", False
        else:
            has_body = True
        while len(p) > size:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(p[:size])
            p = p[size - overlap :]
        if len(current) + len(p) + 1 > size:
            chunks.append(current)
            current = current[-overlap:] + " " + p if overlap else p
        else:
            current = f"{current} {p}".strip()
    if current:
        chunks.append(current)
    return chunks


async def ingest(document_id: int, content: str) -> None:
    """Indexa o texto do documento. Erros ficam gravados no documento para o painel mostrar."""
    with SessionLocal() as db:
        doc = db.get(Document, document_id)
        agent = db.get(AgentProfile, doc.agent_id)
        try:
            pieces = chunk_text(content)
            if not pieces:
                raise ValueError("nenhum texto encontrado no documento")
            provider = build_embedding(agent.embedding or DEFAULT_EMBEDDING)
            vectors = await provider.embed(pieces)
            db.execute(delete(Chunk).where(Chunk.document_id == doc.id))
            db.add_all(
                Chunk(document_id=doc.id, agent_id=agent.id, content=c, embedding=v, embedding_model=provider.model_id)
                for c, v in zip(pieces, vectors)
            )
            doc.status, doc.error, doc.chunk_count = "ready", "", len(pieces)
        except Exception as e:
            logger.exception("falha ao indexar documento %s", document_id)
            doc.status, doc.error = "error", str(e)[:500]
        db.commit()


_providers: dict[str, object] = {}


def _provider(agent: AgentProfile):
    """Reaproveita o cliente HTTP do embedding entre buscas (criar um por busca custava centenas de ms)."""
    spec = agent.embedding or DEFAULT_EMBEDDING
    key = embedding_model_id(spec)
    if key not in _providers:
        _providers[key] = build_embedding(spec)
    return _providers[key]


def _nearest(agent_id: int, model_id: str, vector: list[float], k: int) -> list[tuple[str, float]]:
    with SessionLocal() as db:
        distance = Chunk.embedding.cosine_distance(vector)
        rows = db.execute(
            select(Chunk.content, (1 - distance).label("score"))
            .where(Chunk.agent_id == agent_id, Chunk.embedding_model == model_id)
            .order_by(distance)
            .limit(k)
        ).all()
    return [(r.content, float(r.score)) for r in rows]


async def search(agent: AgentProfile, query: str, k: int = 4) -> list[tuple[str, float]]:
    """Retorna [(trecho, score)], score = similaridade de cosseno (1 = idêntico)."""
    provider = _provider(agent)
    [vector] = await provider.embed([query])
    # Consulta síncrona fora do loop: no worker, travar o loop atrasa o áudio da chamada.
    return await asyncio.to_thread(_nearest, agent.id, provider.model_id, vector, k)


# ~5 mil tokens: cabe no prompt com cache barato e elimina a busca (0,5–1,5 s por pergunta).
INLINE_MAX_CHARS = 20000


def inline_knowledge(agent: AgentProfile, max_chars: int = INLINE_MAX_CHARS) -> str | None:
    """Base inteira como texto, se for pequena; None = grande demais, usar busca."""
    with SessionLocal() as db:
        docs = db.execute(
            select(Document.name, Document.content)
            .where(Document.agent_id == agent.id, Document.status == "ready")
            .order_by(Document.id)
        ).all()
    text_ = "\n\n".join(f"## {d.name}\n{d.content.strip()}" for d in docs)
    return text_ if len(text_) <= max_chars else None


def model_mismatch_count(agent: AgentProfile) -> int:
    """Chunks indexados com outro modelo de embedding (precisam de reindexação)."""
    model_id = embedding_model_id(agent.embedding or DEFAULT_EMBEDDING)
    with SessionLocal() as db:
        return db.execute(
            text("SELECT count(*) FROM chunks WHERE agent_id = :a AND embedding_model <> :m"),
            {"a": agent.id, "m": model_id},
        ).scalar_one()
