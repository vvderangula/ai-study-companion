"""Intelligent workflows: registers background jobs and the event handlers that trigger them.

  MATERIAL_UPLOADED            -> process_material job
  MATERIAL_PROCESSED           -> recommendation (if none active)
  QUIZ_COMPLETED               -> post_quiz job: weak-concept detection, pattern notes, recommendation
  TUTOR_INTERACTION_COMPLETED  -> post_tutor job: distil durable learner context

Importing this module wires everything up; ``app.main`` imports it at startup.
"""

from __future__ import annotations

import logging

from app.core import db as dbm
from app.core.config import settings
from app.services import events, jobs
from app.services.ai.provider import AIClient
from app.services.learning import context as ctx_mod
from app.services.learning import recommendations
from app.services.learning.mastery import growth_for_project
from app.services.materials.processing import process_material

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- jobs


@jobs.job("process_material")
def _process_material(job: dict) -> dict:
    material_id = job["ref_id"]
    events.emit(events.Event(type=events.MATERIAL_PROCESSING_STARTED, user_id=job["user_id"], project_id=job["project_id"], ref_id=material_id, dedupe_key=f"proc_start:{material_id}:{job['attempts']}"))
    try:
        result = process_material(job)
    except Exception as exc:  # noqa: BLE001
        material = dbm.get(dbm.MATERIALS, material_id) or {}
        if material.get("status") == "failed":
            events.emit(events.Event(type=events.MATERIAL_FAILED, user_id=job["user_id"], project_id=job["project_id"], ref_id=material_id, ref_title=material.get("title"), data={"error": str(exc)[:300]}, dedupe_key=f"proc_failed:{material_id}"))
        raise
    material = dbm.get(dbm.MATERIALS, material_id) or {}
    events.emit(events.Event(type=events.MATERIAL_PROCESSED, user_id=job["user_id"], project_id=job["project_id"], ref_id=material_id, ref_title=material.get("title"), data=result, dedupe_key=f"processed:{material_id}"))
    return result


@jobs.job("post_quiz")
def _post_quiz(job: dict) -> dict:
    project = dbm.get(dbm.PROJECTS, job["project_id"])
    if project is None:
        return {}
    user_id = job["user_id"]
    growth = growth_for_project(project["_id"])
    weak = [g for g in growth if g.attempts >= 2 and g.band == "weak"]
    strong = [g for g in growth if g.attempts >= 2 and g.band == "strong"]
    for g in weak:
        ctx_mod.deactivate_notes(user_id, project["_id"], "strength", g.concept_id)
        ctx_mod.add_note(user_id, project["_id"], "weakness", f"Repeatedly struggles with {g.name} (mastery {int(g.score * 100)}% after {g.attempts} attempts).", concept_id=g.concept_id, dedupe_key=f"weakness:{g.concept_id}")
    for g in strong:
        ctx_mod.deactivate_notes(user_id, project["_id"], "weakness", g.concept_id)
        ctx_mod.add_note(user_id, project["_id"], "strength", f"Consistently demonstrates {g.name} (mastery {int(g.score * 100)}%).", concept_id=g.concept_id, dedupe_key=f"strength:{g.concept_id}")
    # repeated-mistake pattern: same concept wrong on the last two quizzes
    wrong = list(dbm.get_db()[dbm.QUIZ_QUESTIONS].find({"project_id": project["_id"], "is_correct": False}, {"concept_name": 1, "concept_id": 1, "session_id": 1}).sort("answered_at", -1).limit(12))
    by_concept: dict[str, set] = {}
    for q in wrong:
        by_concept.setdefault(q.get("concept_id") or "", set()).add(q["session_id"])
    for cid, sessions in by_concept.items():
        if cid and len(sessions) >= 2:
            name = next((q["concept_name"] for q in wrong if q.get("concept_id") == cid), "a concept")
            ctx_mod.add_note(user_id, project["_id"], "pattern", f"Has answered {name} incorrectly across {len(sessions)} different quizzes; needs a different explanation approach.", concept_id=cid, dedupe_key=f"pattern:{cid}")
    rec = recommendations.generate(project, user_id, trigger="quiz_completed")
    return {"weak": len(weak), "strong": len(strong), "recommendation_id": rec["_id"]}


@jobs.job("post_tutor")
def _post_tutor(job: dict) -> dict:
    payload = job["payload"]
    stored = ctx_mod.distil_exchange(AIClient(), job["user_id"], job["project_id"], payload.get("user_message", ""), payload.get("assistant_message", ""))
    return {"notes_stored": stored}


@jobs.job("recommend")
def _recommend(job: dict) -> dict:
    project = dbm.get(dbm.PROJECTS, job["project_id"])
    if project is None:
        return {}
    rec = recommendations.generate(project, job["user_id"], trigger=job["payload"].get("trigger", "system"))
    return {"recommendation_id": rec["_id"]}


# --------------------------------------------------------------------------- event handlers


@events.on(events.MATERIAL_UPLOADED)
def _on_material_uploaded(event: events.Event) -> None:
    job = jobs.enqueue("process_material", user_id=event.user_id, project_id=event.project_id, ref_id=event.ref_id, dedupe_key=f"process:{event.ref_id}")
    if job:
        dbm.update(dbm.MATERIALS, {"_id": event.ref_id}, {"job_id": job["_id"]})


@events.on(events.MATERIAL_PROCESSED)
def _on_material_processed(event: events.Event) -> None:
    if not recommendations.current(event.project_id):
        jobs.enqueue("recommend", user_id=event.user_id, project_id=event.project_id, payload={"trigger": "material_processed"}, dedupe_key=f"recommend:{event.project_id}")


@events.on(events.QUIZ_COMPLETED)
def _on_quiz_completed(event: events.Event) -> None:
    jobs.enqueue("post_quiz", user_id=event.user_id, project_id=event.project_id, ref_id=event.ref_id, dedupe_key=f"post_quiz:{event.ref_id}")


@events.on(events.TUTOR_INTERACTION_COMPLETED)
def _on_tutor_completed(event: events.Event) -> None:
    if not event.data.get("grounded"):
        return  # refusals rarely reveal durable context; save the call
    jobs.enqueue("post_tutor", user_id=event.user_id, project_id=event.project_id, ref_id=event.data.get("message_id"), payload=event.data, dedupe_key=f"post_tutor:{event.data.get('message_id')}")


def requeue_stale_materials() -> int:
    """On startup, re-queue materials left 'processing' by a previous process (thread jobs don't survive restarts)."""
    count = 0
    for m in dbm.get_db()[dbm.MATERIALS].find({"status": {"$in": ["queued", "processing"]}}):
        dbm.get_db()[dbm.JOBS].update_many({"ref_id": m["_id"], "status": {"$in": ["queued", "running"]}}, {"$set": {"status": "failed", "error": "process restarted"}})
        if jobs.enqueue("process_material", user_id=m["user_id"], project_id=m["project_id"], ref_id=m["_id"], dedupe_key=f"process:{m['_id']}"):
            count += 1
    if count:
        logger.info("re-queued %s stale materials (backend=%s)", count, settings.job_backend)
    return count
