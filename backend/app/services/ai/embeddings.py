"""Embedding backends: local ONNX model (fastembed) or a deterministic hash for tests."""

from __future__ import annotations

import hashlib
import logging
import math
import re

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    dim = settings.embedding_dim

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class FastEmbedService(EmbeddingService):
    def __init__(self) -> None:
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name=settings.embedding_model)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return [vec.tolist() for vec in self._model.embed(texts, batch_size=32)]

    def embed_query(self, text: str) -> list[float]:
        return next(self._model.query_embed(text)).tolist()


class HashEmbeddingService(EmbeddingService):
    """Bag-of-words hashed into a fixed vector. Retrieval quality is crude but deterministic."""

    _token = re.compile(r"[a-z0-9]+")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dim
            for tok in self._token.findall(text.lower()):
                h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
                vec[h % self.dim] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    global _service
    if _service is None:
        if settings.embedding_backend == "hash":
            _service = HashEmbeddingService()
        else:
            try:
                _service = FastEmbedService()
            except Exception as exc:  # noqa: BLE001
                logger.warning("fastembed unavailable (%s); falling back to hash embeddings", exc)
                _service = HashEmbeddingService()
    return _service


def set_embedding_service(service: EmbeddingService | None) -> None:
    global _service
    _service = service
