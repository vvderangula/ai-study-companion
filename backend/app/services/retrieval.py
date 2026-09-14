"""Project-scoped semantic retrieval.

Embeddings live on chunk documents; similarity is computed in-process with numpy
over the project's chunks (a project holds at most a few thousand chunks, so this
is fast and needs no vector index). Isolation is enforced here: every query is
filtered on project_id; callers must already have verified ownership.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from app.core import db as dbm
from app.core.config import settings
from app.services.ai.embeddings import get_embedding_service


@dataclass
class Hit:
    chunk_id: str
    material_id: str
    material_title: str
    page_start: int
    page_end: int
    text: str
    score: float
    kind: str

    @property
    def label(self) -> str:
        pages = f"p.{self.page_start}" if self.page_start == self.page_end else f"pp.{self.page_start}-{self.page_end}"
        return f"{self.material_title}, {pages}"

    def to_citation(self, index: int) -> dict:
        return {"label": f"S{index}", "material_id": self.material_id, "material_title": self.material_title, "page": self.page_start, "page_end": self.page_end, "chunk_id": self.chunk_id, "score": round(self.score, 3), "snippet": self.text[:240]}


@dataclass
class RetrievalResult:
    query: str
    hits: list[Hit]
    latency_ms: int
    top_k: int

    @property
    def has_evidence(self) -> bool:
        return any(h.score >= settings.evidence_min_similarity for h in self.hits)

    @property
    def best_score(self) -> float:
        return max((h.score for h in self.hits), default=0.0)

    def to_log(self) -> dict:
        return {
            "query": self.query[:300],
            "top_k": self.top_k,
            "latency_ms": self.latency_ms,
            "best_score": round(self.best_score, 3),
            "has_evidence": self.has_evidence,
            "hits": [{"chunk_id": h.chunk_id, "material": h.material_title, "page": h.page_start, "score": round(h.score, 3)} for h in self.hits],
        }


def _ready_materials(project_id: str) -> dict[str, str]:
    return {m["_id"]: m["title"] for m in dbm.get_db()[dbm.MATERIALS].find({"project_id": project_id, "status": "ready"}, {"title": 1})}


def search(project_id: str, query: str, *, top_k: int | None = None, material_ids: list[str] | None = None) -> RetrievalResult:
    top_k = top_k or settings.retrieval_top_k
    started = time.perf_counter()
    titles = _ready_materials(project_id)
    if material_ids:
        titles = {k: v for k, v in titles.items() if k in material_ids}
    if not titles:
        return RetrievalResult(query=query, hits=[], latency_ms=0, top_k=top_k)

    qvec = np.asarray(get_embedding_service().embed_query(query), dtype=np.float32)
    cursor = dbm.get_db()[dbm.CHUNKS].find({"project_id": project_id, "material_id": {"$in": list(titles)}}, {"embedding": 1, "text": 1, "page_start": 1, "page_end": 1, "material_id": 1, "kind": 1})
    docs = list(cursor)
    if not docs:
        return RetrievalResult(query=query, hits=[], latency_ms=int((time.perf_counter() - started) * 1000), top_k=top_k)

    matrix = np.asarray([d["embedding"] for d in docs], dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1) * (np.linalg.norm(qvec) or 1.0)
    norms[norms == 0] = 1.0
    sims = matrix @ qvec / norms
    order = np.argsort(-sims)[:top_k]
    hits = [
        Hit(chunk_id=docs[i]["_id"], material_id=docs[i]["material_id"], material_title=titles.get(docs[i]["material_id"], "Document"), page_start=docs[i]["page_start"], page_end=docs[i]["page_end"], text=docs[i]["text"], score=float(max(0.0, sims[i])), kind=docs[i].get("kind", "text"))
        for i in order
    ]
    return RetrievalResult(query=query, hits=hits, latency_ms=int((time.perf_counter() - started) * 1000), top_k=top_k)


def chunks_for_pages(project_id: str, material_id: str, pages: list[int], limit: int = 5) -> list[Hit]:
    """Chunks covering the given pages of a material (grounds quiz questions on a concept's source pages)."""
    if not pages:
        return []
    material = dbm.get(dbm.MATERIALS, material_id)
    title = material["title"] if material else "Document"
    cursor = dbm.get_db()[dbm.CHUNKS].find({"project_id": project_id, "material_id": material_id, "page_start": {"$lte": max(pages)}, "page_end": {"$gte": min(pages)}}, {"embedding": 0}).sort("ordinal", 1).limit(limit)
    return [Hit(chunk_id=d["_id"], material_id=material_id, material_title=title, page_start=d["page_start"], page_end=d["page_end"], text=d["text"], score=1.0, kind=d.get("kind", "text")) for d in cursor]


def format_evidence(hits: list[Hit]) -> str:
    if not hits:
        return "(no relevant passages found)"
    return "\n\n".join(f"[S{i}] ({h.label})\n{h.text}" for i, h in enumerate(hits, start=1))
