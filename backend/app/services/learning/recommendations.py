"""Learning recommendations: turn learner state into one clear next action.

A rule layer decides the *kind* of action from evidence (no materials, no
assessments yet, weak concepts, recent decline, everything strong). The model
then phrases a specific, personalised title and reason via structured output.
If the model is unavailable the rule layer's wording is used, so the user
always gets a next step.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel

from app.core import db as dbm
from app.core.errors import AIUnavailableError
from app.models import Recommendation
from app.services import events
from app.services.ai.provider import AIClient, CallContext
from app.services.learning import context as ctx_mod
from app.services.learning.mastery import ConceptGrowth, growth_for_project, overall_mastery
from app.services.prompts.registry import RECOMMEND

logger = logging.getLogger(__name__)


class RecommendationOut(BaseModel):
    action: str
    title: str
    reason: str
    concept_names: list[str]
    suggested_prompt: str = ""


def _rule_candidate(project: dict, growth: list[ConceptGrowth], material_count: int, ready_count: int) -> tuple[str, str, str, list[ConceptGrowth]]:
    if material_count == 0:
        return "upload", "Upload your first learning material", "This project has no materials yet, so the tutor and quizzes have nothing to work from. Add a PDF to get started.", []
    if ready_count == 0:
        return "upload", "Wait for your material to finish processing", "Your material is still being processed. Once it is ready you can start with the tutor or a quiz.", []
    assessed = [g for g in growth if g.attempts > 0]
    if not assessed:
        return "quiz", "Take a short diagnostic quiz", "You haven't been assessed yet. A five-question quiz will map your starting mastery across the concepts in this project.", growth[:3]
    declining = [g for g in assessed if g.trend == "needs_attention"]
    weak = sorted((g for g in assessed if g.band == "weak"), key=lambda g: g.score)
    unassessed = [g for g in growth if g.attempts == 0]
    if declining:
        g = declining[0]
        return "review", f"Review {g.name} before your next quiz", f"Your mastery of {g.name} moved from {int(g.previous * 100)}% to {int(g.score * 100)}%. Re-read the source pages, then ask the tutor to check your understanding.", declining[:2]
    if weak:
        g = weak[0]
        return "tutor", f"Ask the tutor to explain {g.name}", f"{g.name} is your weakest assessed concept at {int(g.score * 100)}%. A focused explanation followed by a quiz is the fastest way to lift it.", weak[:2]
    if unassessed:
        return "quiz", "Quiz the concepts you haven't covered yet", f"{len(unassessed)} concepts have no evidence yet, including {unassessed[0].name}. A quiz will fill in the picture.", unassessed[:3]
    return "quiz", "Take a harder quiz to consolidate", f"All assessed concepts are above {int(min(g.score for g in assessed) * 100)}%. A harder quiz will confirm you can apply them, not just recall them.", sorted(assessed, key=lambda g: g.score)[:2]


def generate(project: dict, user_id: str, trigger: str = "manual") -> dict:
    project_id = project["_id"]
    db = dbm.get_db()
    growth = growth_for_project(project_id)
    material_count = db[dbm.MATERIALS].count_documents({"project_id": project_id})
    ready_count = db[dbm.MATERIALS].count_documents({"project_id": project_id, "status": "ready"})
    action, title, reason, targets = _rule_candidate(project, growth, material_count, ready_count)
    suggested_prompt = ""

    if action in ("review", "tutor", "quiz") and growth:
        state = "\n".join([
            f"Overall mastery: {int(overall_mastery(growth) * 100)}%",
            "Concepts: " + "; ".join(f"{g.name} {int(g.score * 100)}% ({g.trend}, {g.attempts} attempts)" for g in growth[:10]),
            ctx_mod.compose(user_id, project, growth),
            f"Rule-based suggestion: action={action}, targets={[g.name for g in targets]}",
        ])
        try:
            parsed, _ = AIClient().generate_structured(
                CallContext(feature="recommend", user_id=user_id, project_id=project_id, prompt_name=RECOMMEND.name, prompt_version=RECOMMEND.version),
                RecommendationOut,
                system=RECOMMEND.render(project_name=project["name"], learning_goal=project.get("learning_goal") or "not specified", trigger=trigger, state=state),
                messages=[{"role": "user", "content": "Produce the recommendation."}], max_tokens=500, tier="fast",
            )
            if parsed.action in ("quiz", "tutor", "review", "upload") and parsed.title and parsed.reason:
                action, title, reason, suggested_prompt = parsed.action, parsed.title[:200], parsed.reason[:600], parsed.suggested_prompt[:300]
                names = {g.name.lower(): g for g in growth}
                matched = [names[n.lower()] for n in parsed.concept_names if n.lower() in names]
                if matched:
                    targets = matched[:3]
        except AIUnavailableError as exc:
            logger.warning("recommendation model unavailable, using rule wording: %s", exc)

    db[dbm.RECOMMENDATIONS].update_many({"project_id": project_id, "status": "active"}, {"$set": {"status": "superseded"}})
    doc = Recommendation(
        project_id=project_id, user_id=user_id, action=action, title=title, reason=reason,
        concept_ids=[g.concept_id for g in targets], concept_names=[g.name for g in targets],
        payload={"suggested_prompt": suggested_prompt, "pages": targets[0].source_pages[:5] if targets else [], "material_id": targets[0].source_material_id if targets else None},
        trigger=trigger,
    ).to_doc()
    dbm.insert(dbm.RECOMMENDATIONS, doc)
    events.emit(events.Event(type=events.RECOMMENDATION_GENERATED, user_id=user_id, project_id=project_id, ref_id=doc["_id"], ref_title=title, data={"action": action, "trigger": trigger}))
    return doc


def current(project_id: str) -> dict | None:
    return dbm.get_db()[dbm.RECOMMENDATIONS].find_one({"project_id": project_id, "status": "active"}, sort=[("created_at", -1)])
