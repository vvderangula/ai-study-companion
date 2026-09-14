from fastapi import APIRouter, Depends, status

from app.core import db as dbm
from app.core.auth import get_current_user
from app.core.errors import NotFoundError, ValidationFailed
from app.schemas import GlobalNoteCreate
from app.services.analytics import service as analytics
from app.services.learning import context as ctx_mod

router = APIRouter(tags=["analytics"])


@router.get("/home")
def home(user: dict = Depends(get_current_user)):
    return analytics.home(user)


@router.get("/analytics")
def global_analytics(user: dict = Depends(get_current_user)):
    return analytics.global_analytics(user)


# --------------------------------------------------------------------------- global learning context


@router.get("/context")
def global_context(user: dict = Depends(get_current_user)):
    return ctx_mod.global_context(user["_id"])


@router.post("/context/notes", status_code=status.HTTP_201_CREATED)
def add_global_note(body: GlobalNoteCreate, user: dict = Depends(get_current_user)):
    try:
        note = ctx_mod.add_global_note(user["_id"], body.kind, body.content)
    except ValueError as exc:
        raise ValidationFailed(str(exc)) from exc
    return dbm.serialize(note)


@router.delete("/context/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_global_note(note_id: str, user: dict = Depends(get_current_user)):
    result = dbm.get_db()[dbm.LEARNER_NOTES].update_one(
        {"_id": note_id, "user_id": user["_id"], "project_id": None, "active": True}, {"$set": {"active": False}}
    )
    if result.matched_count == 0:
        raise NotFoundError("Note not found.")
