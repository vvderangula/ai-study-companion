"""Persistent learner context.

Durable notes about the learner (goals, strengths, weaknesses, preferences,
tutor observations) live in ``learner_notes``. ``compose`` builds the compact
context block sent to AI prompts: it selects what is relevant now rather than
dumping history. ``distil_exchange`` asks the model whether a tutor exchange
revealed anything worth remembering.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel

from app.core import db as dbm
from app.models import LearnerNote
from app.services.ai.provider import AIClient, CallContext
from app.services.learning.mastery import ConceptGrowth, growth_for_project
from app.services.prompts.registry import CONTEXT_UPDATE

logger = logging.getLogger(__name__)

MAX_NOTES_PER_KIND = 3
MAX_MISTAKES = 3

# Kinds allowed at user level (global). Deliberately excludes concept-bound kinds
# ("weakness", "strength", "pattern"): those are project knowledge and must stay
# scoped to their project so one project's tutor never sees another's subject
# matter. Global notes carry how the learner likes to learn, not what they know.
GLOBAL_KINDS = {"goal", "preference"}


def add_note(user_id: str, project_id: str | None, kind: str, content: str, *, concept_id: str | None = None, source: str = "system", weight: float = 1.0, dedupe_key: str | None = None) -> dict | None:
    content = content.strip()
    if not content:
        return None
    coll = dbm.get_db()[dbm.LEARNER_NOTES]
    key = dedupe_key or f"{kind}:{project_id}:{content.lower()[:80]}"
    existing = coll.find_one({"user_id": user_id, "dedupe_key": key})
    if existing:
        dbm.update(dbm.LEARNER_NOTES, {"_id": existing["_id"]}, {"active": True, "weight": min(3.0, existing.get("weight", 1.0) + 0.5), "content": content})
        return existing
    doc = LearnerNote(user_id=user_id, project_id=project_id, kind=kind, content=content[:400], concept_id=concept_id, source=source, weight=weight, dedupe_key=key).to_doc()
    dbm.insert(dbm.LEARNER_NOTES, doc)
    return doc


def deactivate_notes(user_id: str, project_id: str, kind: str, concept_id: str) -> None:
    dbm.get_db()[dbm.LEARNER_NOTES].update_many({"user_id": user_id, "project_id": project_id, "kind": kind, "concept_id": concept_id}, {"$set": {"active": False}})


def active_notes(user_id: str, project_id: str) -> list[dict]:
    return list(dbm.get_db()[dbm.LEARNER_NOTES].find({"user_id": user_id, "active": True, "$or": [{"project_id": project_id}, {"project_id": None}]}).sort([("weight", -1), ("updated_at", -1)]).limit(30))


def global_notes(user_id: str) -> list[dict]:
    """User-level notes (project_id None) that apply across every project."""
    return list(dbm.get_db()[dbm.LEARNER_NOTES].find({"user_id": user_id, "active": True, "project_id": None}).sort([("weight", -1), ("updated_at", -1)]).limit(30))


def add_global_note(user_id: str, kind: str, content: str, *, source: str = "user") -> dict | None:
    if kind not in GLOBAL_KINDS:
        raise ValueError(f"'{kind}' is project-scoped; global notes accept {sorted(GLOBAL_KINDS)}.")
    return add_note(user_id, None, kind, content, source=source)


def global_context(user_id: str) -> dict:
    """Structured global learning context for the user-level dashboard."""
    notes = global_notes(user_id)
    return {
        "notes": [dbm.serialize(n) for n in notes],
        "counts": {kind: sum(1 for n in notes if n["kind"] == kind) for kind in sorted(GLOBAL_KINDS)},
        "prompt_block": global_block(notes),
    }


def global_block(notes: list[dict] | None = None, user_id: str | None = None) -> str:
    """The global slice of the prompt context: how this learner likes to learn."""
    notes = global_notes(user_id) if notes is None else notes
    by_kind: dict[str, list[str]] = {}
    for note in notes:
        bucket = by_kind.setdefault(note["kind"], [])
        if len(bucket) < MAX_NOTES_PER_KIND:
            bucket.append(note["content"])
    lines = [f"{kind.title()}: " + "; ".join(by_kind[kind]) for kind in ("goal", "preference") if by_kind.get(kind)]
    return "\n".join(lines)


def recent_mistakes(project_id: str, limit: int = MAX_MISTAKES) -> list[dict]:
    return list(dbm.get_db()[dbm.QUIZ_QUESTIONS].find({"project_id": project_id, "is_correct": False, "answered_at": {"$ne": None}}, {"prompt": 1, "concept_name": 1, "feedback": 1, "difficulty": 1, "answered_at": 1}).sort("answered_at", -1).limit(limit))


def compose(user_id: str, project: dict, growth: list[ConceptGrowth] | None = None) -> str:
    """Compact, relevant learner context for prompts (aim for < 1500 chars)."""
    project_id = project["_id"]
    growth = growth if growth is not None else growth_for_project(project_id)
    lines: list[str] = []
    if project.get("learning_goal"):
        lines.append(f"Goal: {project['learning_goal']}")

    assessed = [g for g in growth if g.attempts > 0]
    if assessed:
        weak = sorted((g for g in assessed if g.band == "weak"), key=lambda g: g.score)[:4]
        strong = sorted((g for g in assessed if g.band == "strong"), key=lambda g: -g.score)[:3]
        improving = [g.name for g in assessed if g.trend == "improving"][:3]
        if weak:
            lines.append("Weak concepts: " + ", ".join(f"{g.name} ({int(g.score * 100)}%)" for g in weak))
        if strong:
            lines.append("Strong concepts: " + ", ".join(f"{g.name} ({int(g.score * 100)}%)" for g in strong))
        if improving:
            lines.append("Improving: " + ", ".join(improving))
    else:
        lines.append("No assessments yet; mastery unknown.")

    notes = active_notes(user_id, project_id)
    by_kind: dict[str, list[str]] = {}
    for note in (n for n in notes if n.get("project_id")):
        bucket = by_kind.setdefault(note["kind"], [])
        if len(bucket) < MAX_NOTES_PER_KIND:
            bucket.append(note["content"])
    for kind in ("preference", "weakness", "strength", "tutor_note", "pattern", "goal"):
        if by_kind.get(kind):
            lines.append(f"{kind.replace('_', ' ').title()}: " + "; ".join(by_kind[kind]))

    # Global notes apply to every project, so label them as the learner's own
    # standing preferences rather than as facts about this project's material.
    across = global_block([n for n in notes if not n.get("project_id")])
    if across:
        lines.append("About this learner (applies across all their projects):\n" + across)

    mistakes = recent_mistakes(project_id)
    if mistakes:
        lines.append("Recent mistakes: " + "; ".join(f"{m.get('concept_name') or 'general'} - {m['prompt'][:70]}" for m in mistakes))
    return "\n".join(lines)


def dashboard_context(user_id: str, project: dict, growth: list[ConceptGrowth]) -> dict:
    """Structured version of the context for the project dashboard."""
    notes = active_notes(user_id, project["_id"])
    return {
        "goal": project.get("learning_goal", ""),
        "weak": [g.to_dict() for g in sorted((g for g in growth if g.attempts and g.band == "weak"), key=lambda g: g.score)[:4]],
        "strong": [g.to_dict() for g in sorted((g for g in growth if g.attempts and g.band == "strong"), key=lambda g: -g.score)[:4]],
        "notes": [dbm.serialize(n) for n in notes if n.get("project_id")][:8],
        "global_notes": [dbm.serialize(n) for n in notes if not n.get("project_id")][:8],
        "recent_mistakes": [dbm.serialize(m) for m in recent_mistakes(project["_id"])],
    }


# --------------------------------------------------------------------------- distillation


class NoteOut(BaseModel):
    kind: str
    content: str
    concept_name: str | None = None


class NoteList(BaseModel):
    notes: list[NoteOut]


ALLOWED_KINDS = {"goal", "preference", "weakness", "strength", "tutor_note"}


def distil_exchange(ai: AIClient, user_id: str, project_id: str, user_message: str, assistant_message: str) -> int:
    system = CONTEXT_UPDATE.render(user_message=user_message[:1500], assistant_message=assistant_message[:2500])
    parsed, _ = ai.generate_structured(
        CallContext(feature="context_update", user_id=user_id, project_id=project_id, prompt_name=CONTEXT_UPDATE.name, prompt_version=CONTEXT_UPDATE.version),
        NoteList, system=system, messages=[{"role": "user", "content": "Return the notes list."}], max_tokens=600, tier="fast",
    )
    concepts = {c["name"].lower(): c["_id"] for c in dbm.get_db()[dbm.CONCEPTS].find({"project_id": project_id}, {"name": 1})}
    stored = 0
    for note in parsed.notes[:3]:
        if note.kind not in ALLOWED_KINDS or len(note.content) < 8:
            continue
        concept_id = concepts.get((note.concept_name or "").lower())
        if add_note(user_id, project_id, note.kind, note.content, concept_id=concept_id, source="tutor"):
            stored += 1
    return stored
