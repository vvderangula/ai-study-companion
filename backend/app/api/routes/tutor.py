import json
import logging

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from app.core import db as dbm
from app.core.auth import get_current_user
from app.schemas import TutorAsk
from app.services.learning import workspace
from app.services.tutor import service as tutor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/tutor", tags=["tutor"])


@router.get("/conversations")
def list_conversations(project_id: str, user: dict = Depends(get_current_user)):
    project = workspace.get_project(user["_id"], project_id)
    rows = dbm.get_db()[dbm.CONVERSATIONS].find({"project_id": project["_id"], "user_id": user["_id"]}).sort("updated_at", -1).limit(30)
    return [dbm.serialize(c) for c in rows]


@router.get("/conversations/{conversation_id}")
def get_conversation(project_id: str, conversation_id: str, user: dict = Depends(get_current_user)):
    project = workspace.get_project(user["_id"], project_id)
    conv = tutor.get_or_create_conversation(project, user["_id"], conversation_id)
    return {"conversation": dbm.serialize(conv), "messages": [dbm.serialize(m) for m in tutor.list_messages(conv["_id"])]}


@router.post("/ask")
def ask(project_id: str, body: TutorAsk, user: dict = Depends(get_current_user)):
    """Server-sent events: meta -> tool* -> delta* -> done | error."""
    project = workspace.get_project(user["_id"], project_id)
    conv = tutor.get_or_create_conversation(project, user["_id"], body.conversation_id)

    def stream():
        try:
            for event in tutor.ask(project, user, conv, body.message):
                yield {"event": event["type"], "data": json.dumps(event, default=str)}
        except Exception as exc:  # noqa: BLE001
            logger.exception("tutor stream failed")
            yield {"event": "error", "data": json.dumps({"type": "error", "message": tutor.friendly_error(exc), "retryable": True})}

    return EventSourceResponse(stream(), ping=15)


@router.post("/ask/sync")
def ask_sync(project_id: str, body: TutorAsk, user: dict = Depends(get_current_user)):
    """Non-streaming variant (tests, simple clients)."""
    project = workspace.get_project(user["_id"], project_id)
    conv = tutor.get_or_create_conversation(project, user["_id"], body.conversation_id)
    return tutor.ask_sync(project, user, conv, body.message)
