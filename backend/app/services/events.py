"""Activity events and the event-driven workflow dispatcher.

``emit`` records an activity event (idempotent via dedupe_key) and then routes
it to registered handlers, which run follow-up work. New event types only need
a new handler registration.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from pymongo.errors import DuplicateKeyError

from app.core import db as dbm
from app.models import ActivityEvent

logger = logging.getLogger(__name__)

SPACE_CREATED = "space_created"
PROJECT_CREATED = "project_created"
PROJECT_ACCESSED = "project_accessed"
MATERIAL_UPLOADED = "material_uploaded"
MATERIAL_PROCESSING_STARTED = "material_processing_started"
MATERIAL_PROCESSED = "material_processed"
MATERIAL_FAILED = "material_failed"
CONVERSATION_STARTED = "conversation_started"
TUTOR_QUESTION_ASKED = "tutor_question_asked"
TUTOR_INTERACTION_COMPLETED = "tutor_interaction_completed"
QUIZ_STARTED = "quiz_started"
QUESTION_ANSWERED = "question_answered"
QUIZ_COMPLETED = "quiz_completed"
MASTERY_UPDATED = "mastery_updated"
RECOMMENDATION_GENERATED = "recommendation_generated"

USER_FACING_TYPES = [
    SPACE_CREATED, PROJECT_CREATED, MATERIAL_UPLOADED, MATERIAL_PROCESSED, MATERIAL_FAILED,
    CONVERSATION_STARTED, TUTOR_QUESTION_ASKED, QUIZ_STARTED, QUIZ_COMPLETED, MASTERY_UPDATED,
    RECOMMENDATION_GENERATED,
]

# Events the learner performed themselves; only these define "what were you last doing".
LEARNER_ACTION_TYPES = {PROJECT_CREATED, MATERIAL_UPLOADED, CONVERSATION_STARTED, TUTOR_QUESTION_ASKED, QUIZ_STARTED, QUESTION_ANSWERED, QUIZ_COMPLETED}

LABELS = {
    SPACE_CREATED: "Created a space",
    PROJECT_CREATED: "Created a project",
    PROJECT_ACCESSED: "Opened a project",
    MATERIAL_UPLOADED: "Uploaded material",
    MATERIAL_PROCESSING_STARTED: "Started processing material",
    MATERIAL_PROCESSED: "Material ready",
    MATERIAL_FAILED: "Material processing failed",
    CONVERSATION_STARTED: "Started a tutor conversation",
    TUTOR_QUESTION_ASKED: "Asked the tutor",
    TUTOR_INTERACTION_COMPLETED: "Tutor answered",
    QUIZ_STARTED: "Started a quiz",
    QUESTION_ANSWERED: "Answered a question",
    QUIZ_COMPLETED: "Completed a quiz",
    MASTERY_UPDATED: "Mastery updated",
    RECOMMENDATION_GENERATED: "New recommendation",
}


@dataclass
class Event:
    type: str
    user_id: str | None = None
    space_id: str | None = None
    project_id: str | None = None
    ref_id: str | None = None
    ref_title: str | None = None
    data: dict = field(default_factory=dict)
    dedupe_key: str | None = None


Handler = Callable[[Event], None]
_handlers: dict[str, list[Handler]] = {}


def on(event_type: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        _handlers.setdefault(event_type, []).append(fn)
        return fn

    return register


def emit(event: Event) -> dict | None:
    """Persist the event and run handlers. Returns None if it was a duplicate."""
    doc = ActivityEvent(
        user_id=event.user_id, space_id=event.space_id, project_id=event.project_id, event_type=event.type,
        ref_id=event.ref_id, ref_title=event.ref_title, data=event.data, dedupe_key=event.dedupe_key,
    ).to_doc()
    try:
        dbm.insert(dbm.ACTIVITY, doc)
    except DuplicateKeyError:
        logger.info("duplicate event ignored: %s %s", event.type, event.dedupe_key)
        return None

    if event.project_id and event.type in LEARNER_ACTION_TYPES:
        dbm.update(dbm.PROJECTS, {"_id": event.project_id}, {"last_activity_type": event.type, "last_activity_ref": event.ref_id, "last_accessed_at": doc["created_at"]})

    for handler in _handlers.get(event.type, []):
        try:
            handler(event)
        except Exception:  # noqa: BLE001
            logger.exception("event handler failed for %s", event.type)
    return doc
