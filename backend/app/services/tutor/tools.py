"""Controlled application capabilities exposed to the tutor.

The model may *request* a capability; the backend validates the arguments with
a schema, injects the authenticated user/project scope (model-supplied ids are
never trusted), executes, logs, and returns a compact result. State-changing
capabilities (creating a quiz) are limited and idempotent per turn.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import Any

from pydantic import BaseModel, ValidationError, field_validator

from app.core import db as dbm
from app.services.ai.provider import AIClient, CallContext, ToolSpec
from app.services.learning import context as ctx_mod
from app.services.learning.mastery import ConceptGrowth
from app.services.prompts.registry import TUTOR_ROUTER
from app.services.retrieval import format_evidence, search

logger = logging.getLogger(__name__)

MAX_TOOL_CALLS = 2

ROUTER_SYSTEM = TUTOR_ROUTER.render()


class SearchArgs(BaseModel):
    query: str

    @field_validator("query")
    @classmethod
    def _q(cls, v: str) -> str:
        v = v.strip()
        if not 2 <= len(v) <= 300:
            raise ValueError("query must be 2-300 chars")
        return v


class NoArgs(BaseModel):
    pass


class QuizArgs(BaseModel):
    concept_name: str | None = None
    question_count: int = 5

    @field_validator("question_count")
    @classmethod
    def _n(cls, v: int) -> int:
        return max(3, min(10, int(v)))


TOOLS: list[ToolSpec] = [
    ToolSpec("search_materials", "Search the learner's project materials for passages about a topic.", {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}),
    ToolSpec("get_learning_state", "Get the learner's current mastery per concept, weak areas and trends.", {"type": "object", "properties": {}}),
    ToolSpec("get_recent_mistakes", "Get the learner's most recent incorrect quiz answers with feedback.", {"type": "object", "properties": {}}),
    ToolSpec("start_quiz", "Start an adaptive quiz for the learner, optionally focused on one concept.", {"type": "object", "properties": {"concept_name": {"type": "string"}, "question_count": {"type": "integer"}}}),
]

SCHEMAS: dict[str, type[BaseModel]] = {"search_materials": SearchArgs, "get_learning_state": NoArgs, "get_recent_mistakes": NoArgs, "start_quiz": QuizArgs}


class ToolRunner:
    def __init__(self, ai: AIClient, *, project: dict, user: dict, growth: list[ConceptGrowth]) -> None:
        self.ai = ai
        self.project = project
        self.user = user
        self.growth = growth
        self.results: list[tuple[str, str]] = []

    def run(self, message: str, recent: list[dict]) -> Iterator[dict]:
        ctx = CallContext(feature="tutor_tools", user_id=self.user["_id"], project_id=self.project["_id"], prompt_name=TUTOR_ROUTER.name, prompt_version=TUTOR_ROUTER.version)
        history = [*recent[-2:], {"role": "user", "content": message}]
        result, _ = self.ai.generate(ctx, system=ROUTER_SYSTEM, messages=history, max_tokens=300, tier="fast", tools=TOOLS, temperature=0.0)
        seen: set[str] = set()
        for use in result.tool_uses[:MAX_TOOL_CALLS]:
            if use.name in seen or use.name not in SCHEMAS:
                continue
            seen.add(use.name)
            try:
                args = SCHEMAS[use.name].model_validate(use.input or {})
            except ValidationError as exc:
                yield {"name": use.name, "status": "rejected", "error": str(exc)[:200]}
                continue
            try:
                output = self._execute(use.name, args)
                self.results.append((use.name, output["text"]))
                yield {"name": use.name, "status": "ok", "input": args.model_dump(), "summary": output["summary"], "data": output.get("data")}
            except Exception as exc:  # noqa: BLE001
                logger.warning("tool %s failed: %s", use.name, exc)
                yield {"name": use.name, "status": "error", "error": str(exc)[:200]}

    def context_block(self) -> str:
        if not self.results:
            return ""
        return "<tool_results>\n" + "\n\n".join(f"[{name}]\n{text}" for name, text in self.results) + "\n</tool_results>"

    # --- executors (scope comes from the authenticated request, never from the model) ---

    def _execute(self, name: str, args: BaseModel) -> dict[str, Any]:
        pid = self.project["_id"]
        if name == "search_materials":
            res = search(pid, args.query, top_k=4)
            return {"text": format_evidence(res.hits).replace("[S", "[T"), "summary": f"Searched materials for '{args.query}' ({len(res.hits)} passages)", "data": {"hits": len(res.hits)}}
        if name == "get_learning_state":
            assessed = [g for g in self.growth if g.attempts > 0]
            if not assessed:
                text = "No assessments yet. Mastery is unknown for all concepts: " + ", ".join(g.name for g in self.growth[:10])
            else:
                text = "\n".join(f"- {g.name}: {int(g.score * 100)}% ({g.band}, trend {g.trend}, {g.attempts} attempts)" for g in self.growth)
            return {"text": text, "summary": "Looked up your learning state", "data": {"concepts": len(self.growth)}}
        if name == "get_recent_mistakes":
            mistakes = ctx_mod.recent_mistakes(pid, limit=5)
            text = "\n".join(f"- [{m.get('concept_name') or 'general'}] {m['prompt'][:140]} -> feedback: {(m.get('feedback') or '')[:160]}" for m in mistakes) or "No incorrect answers recorded yet."
            return {"text": text, "summary": f"Reviewed {len(mistakes)} recent mistakes", "data": {"count": len(mistakes)}}
        if name == "start_quiz":
            from app.services.quiz.service import start_session

            concept_id = None
            if args.concept_name:
                match = next((g for g in self.growth if g.name.lower() == args.concept_name.lower()), None)
                concept_id = match.concept_id if match else None
            session = start_session(self.project, self.user, target_questions=args.question_count, focus_concept_id=concept_id, idempotency_key=f"tutor:{self.project['_id']}:{dbm.now().strftime('%Y%m%d%H%M')}")
            return {"text": f"A quiz session was created (id {session['_id']}). Tell the learner it is ready in the Quiz tab and do not ask questions yourself.", "summary": "Started an adaptive quiz", "data": {"quiz_session_id": session["_id"]}}
        raise ValueError(f"unknown tool {name}")


def tool_specs_json() -> str:
    return json.dumps([{"name": t.name, "description": t.description} for t in TOOLS])
