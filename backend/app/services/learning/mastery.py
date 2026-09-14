"""Concept mastery model and growth analysis.

Mastery is an estimate in [0, 1] updated by evidence (quiz answers, tutor checks).
The update is an exponential moving estimate whose learning rate shrinks as
confidence (amount of evidence) grows and whose step is scaled by difficulty: a
correct hard answer moves the score more than a correct easy one, and a wrong
easy answer moves it down more than a wrong hard one.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import timedelta

from app.core import db as dbm
from app.core.config import settings
from app.models import Mastery, MasteryHistory

DIFFICULTY_WEIGHT = {"easy": 0.6, "medium": 1.0, "hard": 1.4}
BASE_ALPHA = 0.35
MIN_ALPHA = 0.12
CONFIDENCE_STEP = 0.15


def ensure_mastery(concept: dict) -> dict:
    coll = dbm.get_db()[dbm.MASTERY]
    row = coll.find_one({"concept_id": concept["_id"]})
    if row is None:
        row = Mastery(concept_id=concept["_id"], project_id=concept["project_id"], user_id=concept["user_id"]).to_doc()
        dbm.insert(dbm.MASTERY, row)
    return row


def compute_update(score: float, confidence: float, result: float, difficulty: str) -> tuple[float, float]:
    """Pure function: returns (new_score, new_confidence)."""
    result = max(0.0, min(1.0, result))
    weight = DIFFICULTY_WEIGHT.get(difficulty, 1.0)
    alpha = max(MIN_ALPHA, BASE_ALPHA / (1.0 + 2.0 * confidence))
    effective = weight if result >= score else 2.0 - weight
    new_score = score + alpha * effective * (result - score)
    return round(max(0.0, min(1.0, new_score)), 4), round(min(1.0, confidence + CONFIDENCE_STEP), 4)


def apply_evidence(concept: dict, *, result: float, difficulty: str, source: str, source_ref: str | None = None) -> dict:
    """Update mastery with one piece of evidence (result in [0,1]). Idempotent per source_ref."""
    mastery = ensure_mastery(concept)
    hist = dbm.get_db()[dbm.MASTERY_HISTORY]
    if source_ref and hist.find_one({"concept_id": concept["_id"], "source_ref": source_ref}):
        return mastery

    previous = mastery["score"]
    new_score, new_conf = compute_update(previous, mastery["confidence"], result, difficulty)
    correct = result >= 0.7
    streak = mastery.get("streak", 0)
    streak = (streak + 1 if streak >= 0 else 1) if correct else (streak - 1 if streak <= 0 else -1)
    fields = {
        "score": new_score,
        "confidence": new_conf,
        "attempts": mastery["attempts"] + 1,
        "correct": mastery["correct"] + (1 if correct else 0),
        "streak": streak,
        "last_result": "correct" if correct else "incorrect",
        "last_assessed_at": dbm.now(),
    }
    dbm.update(dbm.MASTERY, {"_id": mastery["_id"]}, fields)
    dbm.insert(dbm.MASTERY_HISTORY, MasteryHistory(concept_id=concept["_id"], project_id=concept["project_id"], user_id=concept["user_id"], score=new_score, previous_score=previous, source=source, source_ref=source_ref).to_doc())
    return {**mastery, **fields}


# --------------------------------------------------------------------------- growth


@dataclass
class ConceptGrowth:
    concept_id: str
    name: str
    description: str
    score: float
    previous: float
    delta: float
    trend: str  # improving | stable | needs_attention | new
    band: str  # strong | developing | weak
    attempts: int
    confidence: float
    last_result: str | None
    importance: float
    source_pages: list[int]
    source_material_id: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def band_for(score: float) -> str:
    if score >= settings.mastery_threshold_strong:
        return "strong"
    if score >= settings.mastery_threshold_weak:
        return "developing"
    return "weak"


def growth_for_project(project_id: str, window_days: int = 7) -> list[ConceptGrowth]:
    db = dbm.get_db()
    concepts = list(db[dbm.CONCEPTS].find({"project_id": project_id}))
    mastery = {m["concept_id"]: m for m in db[dbm.MASTERY].find({"project_id": project_id})}
    cutoff = dbm.now() - timedelta(days=window_days)
    history_by_concept: dict[str, list[dict]] = {}
    for h in db[dbm.MASTERY_HISTORY].find({"project_id": project_id}).sort("created_at", 1):
        history_by_concept.setdefault(h["concept_id"], []).append(h)

    out: list[ConceptGrowth] = []
    for concept in concepts:
        m = mastery.get(concept["_id"])
        score = m["score"] if m else 0.3
        attempts = m["attempts"] if m else 0
        history = history_by_concept.get(concept["_id"], [])
        if not history:
            previous, trend = score, "new"
        else:
            older = [h for h in history if h["created_at"] < cutoff]
            previous = older[-1]["score"] if older else history[0]["previous_score"]
            delta = score - previous
            if attempts and score < settings.mastery_threshold_weak and delta <= 0.02:
                trend = "needs_attention"
            elif delta >= 0.08:
                trend = "improving"
            elif delta <= -0.08:
                trend = "needs_attention"
            else:
                trend = "stable"
        out.append(ConceptGrowth(
            concept_id=concept["_id"], name=concept["name"], description=concept.get("description", ""),
            score=round(score, 3), previous=round(previous, 3), delta=round(score - previous, 3), trend=trend, band=band_for(score),
            attempts=attempts, confidence=round(m["confidence"], 3) if m else 0.0, last_result=m.get("last_result") if m else None,
            importance=concept.get("importance", 0.5), source_pages=concept.get("source_pages", []), source_material_id=concept.get("source_material_id"),
        ))
    out.sort(key=lambda g: (-g.importance, g.score))
    return out


def overall_mastery(growth: list[ConceptGrowth]) -> float:
    if not growth:
        return 0.0
    total_w = sum(0.5 + g.importance for g in growth)
    return round(sum(g.score * (0.5 + g.importance) for g in growth) / total_w, 3)


def mastery_timeline(project_id: str, days: int = 30) -> list[dict]:
    cutoff = dbm.now() - timedelta(days=days)
    rows = dbm.get_db()[dbm.MASTERY_HISTORY].find({"project_id": project_id, "created_at": {"$gte": cutoff}}).sort("created_at", 1)
    latest: dict[str, float] = {}
    by_day: dict[str, float] = {}
    for row in rows:
        latest[row["concept_id"]] = row["score"]
        by_day[row["created_at"].date().isoformat()] = round(sum(latest.values()) / len(latest), 3)
    return [{"date": d, "mastery": v} for d, v in sorted(by_day.items())]
