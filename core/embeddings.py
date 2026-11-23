"""EmbeddingProvider: interface própria (o LiveKit não tem uma). Vetores de modelos diferentes não se misturam:
trocar o modelo de embedding de um agente exige reindexar os documentos dele."""

from typing import Protocol

from core.config import ProviderSpec


class EmbeddingProvider(Protocol):
    model_id: str  # gravado em cada chunk

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbeddings:
    def __init__(self, model: str):
        from openai import AsyncOpenAI

        self.model_id = f"openai:{model}"
        self._model = model
        self._client = AsyncOpenAI()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), 256):  # limite de itens por requisição
            res = await self._client.embeddings.create(model=self._model, input=texts[i : i + 256])
            out += [d.embedding for d in res.data]
        return out


class GoogleEmbeddings:
    def __init__(self, model: str):
        from google import genai

        self.model_id = f"google:{model}"
        self._model = model
        self._client = genai.Client()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), 100):
            res = await self._client.aio.models.embed_content(model=self._model, contents=texts[i : i + 100])
            out += [e.values for e in res.embeddings]
        return out


_VENDORS = {"openai": OpenAIEmbeddings, "google": GoogleEmbeddings}


def embedding_model_id(spec: ProviderSpec | dict) -> str:
    spec = ProviderSpec.model_validate(spec)
    return f"{spec.vendor}:{spec.model}"


def build_embedding(spec: ProviderSpec | dict) -> EmbeddingProvider:
    spec = ProviderSpec.model_validate(spec)
    if spec.vendor not in _VENDORS:
        raise ValueError(f"embedding: fornecedor '{spec.vendor}' não registrado ({sorted(_VENDORS)})")
    return _VENDORS[spec.vendor](spec.model)
