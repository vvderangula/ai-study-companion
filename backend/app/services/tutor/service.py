"""AI Tutor: grounded, cited, context-aware, streaming.

Pipeline for one turn:
  1. retrieve evidence from the project's materials (project-scoped)
  2. decide whether the evidence is sufficient (similarity threshold)
  3. compose context: learner profile + rolling conversation summary + recent turns
  4. controlled tool phase (fast model, validated tools, user scope injected)
  5. stream the grounded answer; parse citations + GROUNDED flag; persist; emit events
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from typing import Any

from app.core import db as dbm
from app.core.config import settings
from app.core.errors import AIUnavailableError, NotFoundError
from app.models import Conversation, Message
from app.services import events
from app.services.ai.provider import AIClient, CallContext
from app.services.learning import context as ctx_mod
from app.services.learning.mastery import growth_for_project
from app.services.prompts.registry import TUTOR
from app.services.retrieval import RetrievalResult, format_evidence, search
from app.services.tutor.tools import ToolRunner

logger = logging.getLogger(__name__)

# Anything the learner reads when generation fails. Provider strings ("no API key
# configured", raw HTTP errors) are useless to a student and alarming to read, so
# they stay in the logs and the ai_requests trace; the learner gets a next step.
FRIENDLY_ERRORS: dict[str, str] = {
    "ai_rate_limited": "Your tutor is busy right now. Please wait a few seconds and ask again.",
    "ai_timeout": "That took longer than expected. Please try asking again, or shorten your question.",
    "ai_connection": "Couldn't reach your tutor — check your connection and try again.",
    "ai_not_configured": "The tutor isn't set up on this server yet. Please contact whoever is running it.",
    "ai_auth": "The tutor isn't set up correctly on this server. Please contact whoever is running it.",
}
UNAVAILABLE = "Your tutor is temporarily unavailable. Please try again in a moment — nothing you've asked has been lost."
GENERIC_ERROR = "Something went wrong while answering. Please try again in a moment."


def friendly_error(exc: Exception) -> str:
    """Map an exception to a message worth showing a learner."""
    code = getattr(exc, "code", "")
    if code in FRIENDLY_ERRORS:
        return FRIENDLY_ERRORS[code]
    return UNAVAILABLE if isinstance(exc, AIUnavailableError) else GENERIC_ERROR

RECENT_TURNS = 6
_GROUNDED = re.compile(r"\n?\s*GROUNDED:\s*(yes|no)\s*$", re.IGNORECASE)
_CITE = re.compile(r"\[S(\d+)\]")


def get_or_create_conversation(project: dict, user_id: str, conversation_id: str | None) -> dict:
    if conversation_id:
        conv = dbm.find_one(dbm.CONVERSATIONS, {"_id": conversation_id, "project_id": project["_id"], "user_id": user_id})
        if conv is None:
            raise NotFoundError("Conversation not found.")
        return conv
    doc = Conversation(project_id=project["_id"], user_id=user_id).to_doc()
    dbm.insert(dbm.CONVERSATIONS, doc)
    events.emit(events.Event(type=events.CONVERSATION_STARTED, user_id=user_id, project_id=project["_id"], ref_id=doc["_id"], ref_title="New conversation"))
    return doc


def list_messages(conversation_id: str, limit: int = 100) -> list[dict]:
    return list(dbm.get_db()[dbm.MESSAGES].find({"conversation_id": conversation_id}).sort("created_at", 1).limit(limit))


def _history(conversation: dict) -> tuple[str, list[dict]]:
    msgs = list_messages(conversation["_id"])
    recent = msgs[-RECENT_TURNS:]
    older = msgs[:-RECENT_TURNS]
    summary = conversation.get("summary") or ""
    if older and not summary:
        summary = "Earlier in this conversation the learner asked about: " + "; ".join(m["content"][:60] for m in older if m["role"] == "user")[:600]
    return summary or "(start of conversation)", [{"role": m["role"], "content": m["content"]} for m in recent]


def _retrieval_query(message: str, recent: list[dict]) -> str:
    """Short follow-ups ("why?", "give an example") need the previous question for retrieval."""
    if len(message.split()) <= 4 and recent:
        prev_user = next((m["content"] for m in reversed(recent) if m["role"] == "user"), "")
        return f"{prev_user} {message}".strip()
    return message


def ask(project: dict, user: dict, conversation: dict, message: str) -> Iterator[dict]:
    """Yield SSE-ready events: {type: meta|delta|tool|done|error, ...}."""
    project_id, user_id = project["_id"], user["_id"]
    ai = AIClient()
    message = message.strip()
    user_msg = Message(conversation_id=conversation["_id"], project_id=project_id, role="user", content=message).to_doc()
    dbm.insert(dbm.MESSAGES, user_msg)
    events.emit(events.Event(type=events.TUTOR_QUESTION_ASKED, user_id=user_id, project_id=project_id, ref_id=conversation["_id"], ref_title=message[:120]))

    summary, recent = _history(conversation)
    recent = recent[:-1] if recent and recent[-1]["content"] == message else recent

    retrieval: RetrievalResult = search(project_id, _retrieval_query(message, recent))
    growth = growth_for_project(project_id)
    learner_context = ctx_mod.compose(user_id, project, growth)

    # --- controlled tool phase --------------------------------------------------------
    runner = ToolRunner(ai, project=project, user=user, growth=growth)
    tool_events: list[dict] = []
    extra_context = ""
    try:
        for tool_event in runner.run(message, recent):
            tool_events.append(tool_event)
            yield {"type": "tool", **tool_event}
        extra_context = runner.context_block()
    except Exception as exc:  # noqa: BLE001  tools are best-effort; the answer must still flow
        logger.warning("tool phase failed: %s", exc)

    if not retrieval.has_evidence:
        evidence = "(no passages in the project's materials are relevant enough to this question)"
    else:
        evidence = format_evidence(retrieval.hits)
    if extra_context:
        evidence = f"{evidence}\n\n{extra_context}"

    system = TUTOR.render(
        project_name=project["name"], learning_goal=project.get("learning_goal") or "not specified",
        learner_context=learner_context, history_summary=summary, evidence=evidence,
    )
    yield {"type": "meta", "conversation_id": conversation["_id"], "retrieval": retrieval.to_log(), "has_evidence": retrieval.has_evidence}

    ctx = CallContext(feature="tutor", user_id=user_id, project_id=project_id, prompt_name=TUTOR.name, prompt_version=TUTOR.version, retrieval=retrieval.to_log())
    messages = [*recent, {"role": "user", "content": message}]
    full = ""
    ai_request_id = None
    try:
        for item in ai.stream(ctx, system=system, messages=messages, max_tokens=1200):
            if isinstance(item, dict):
                ai_request_id = item["ai_request_id"]
                full = item["text"]
            else:
                full += item
                yield {"type": "delta", "text": item}
    except Exception as exc:  # noqa: BLE001
        logger.exception("tutor generation failed")
        yield {"type": "error", "message": friendly_error(exc), "retryable": True}
        return

    grounded_match = _GROUNDED.search(full)
    grounded = (grounded_match.group(1).lower() == "yes") if grounded_match else retrieval.has_evidence
    answer = _GROUNDED.sub("", full).strip()
    cited = sorted({int(n) for n in _CITE.findall(answer)})
    citations = [retrieval.hits[i - 1].to_citation(i) for i in cited if 0 < i <= len(retrieval.hits)]
    if grounded and not citations and retrieval.hits:
        citations = [retrieval.hits[0].to_citation(1)]

    assistant_msg = Message(conversation_id=conversation["_id"], project_id=project_id, role="assistant", content=answer, citations=citations, tool_calls=tool_events, grounded=grounded, ai_request_id=ai_request_id).to_doc()
    dbm.insert(dbm.MESSAGES, assistant_msg)
    updates: dict[str, Any] = {"message_count": conversation.get("message_count", 0) + 2}
    if conversation.get("title") in (None, "New conversation"):
        updates["title"] = message[:80]
    dbm.update(dbm.CONVERSATIONS, {"_id": conversation["_id"]}, updates)
    if dbm.get_db()[dbm.AI_REQUESTS].find_one({"_id": ai_request_id}) and ai_request_id:
        dbm.update(dbm.AI_REQUESTS, {"_id": ai_request_id}, {"tool_calls": tool_events, "grounded": grounded, "citations": len(citations)})

    events.emit(events.Event(type=events.TUTOR_INTERACTION_COMPLETED, user_id=user_id, project_id=project_id, ref_id=conversation["_id"], data={"grounded": grounded, "citations": len(citations), "user_message": message[:1500], "assistant_message": answer[:2500], "message_id": assistant_msg["_id"]}))
    yield {"type": "done", "message": dbm.serialize(assistant_msg), "grounded": grounded, "citations": citations}


def ask_sync(project: dict, user: dict, conversation: dict, message: str) -> dict:
    """Non-streaming helper (evals, tests). Returns the final 'done' payload or error."""
    final: dict = {}
    for event in ask(project, user, conversation, message):
        if event["type"] in ("done", "error"):
            final = event
    return final
