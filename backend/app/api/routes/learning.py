"""Growth, mastery, recommendations and learner context."""

from fastapi import APIRouter, Depends, status

from app.core import db as dbm
from app.core.auth import get_current_user
from app.core.errors import NotFoundError
from app.schemas import NoteCreate, RecommendationUpdate
from app.services.learning import context as ctx_mod
from app.services.learning import recommendations, workspace
from app.services.learning.mastery import growth_for_project, mastery_timeline, overall_mastery

router = APIRouter(prefix="/projects/{project_id}", tags=["learning"])


@router.get("/growth")
def growth(project_id: str, user: dict = Depends(get_current_user)):
    project = workspace.get_project(user["_id"], project_id)
    g = growth_for_project(project["_id"])
    assessed = [x for x in g if x.attempts]
    return {
        "overall_mastery": overall_mastery(g),
        "concepts": [x.to_dict() for x in g],
        "strong": [x.to_dict() for x in assessed if x.band == "strong"],
        "weak": [x.to_dict() for x in assessed if x.band == "weak"],
        "improving": [x.to_dict() for x in assessed if x.trend == "improving"],
        "stable": [x.to_dict() for x in assessed if x.trend == "stable"],
        "attention": [x.to_dict() for x in assessed if x.trend == "needs_attention"],
        "timeline": mastery_timeline(project["_id"]),
        "history": [dbm.serialize(h) for h in dbm.get_db()[dbm.MASTERY_HISTORY].find({"project_id": project["_id"]}).sort("created_at", -1).limit(50)],
        "recommendation": dbm.serialize(recommendations.current(project["_id"])),
    }


@router.get("/recommendations")
def list_recommendations(project_id: str, user: dict = Depends(get_current_user)):
    project = workspace.get_project(user["_id"], project_id)
    return [dbm.serialize(r) for r in dbm.get_db()[dbm.RECOMMENDATIONS].find({"project_id": project["_id"]}).sort("created_at", -1).limit(10)]


@router.post("/recommendations/generate", status_code=status.HTTP_201_CREATED)
def generate_recommendation(project_id: str, user: dict = Depends(get_current_user)):
    project = workspace.get_project(user["_id"], project_id)
    return dbm.serialize(recommendations.generate(project, user["_id"], trigger="manual"))


@router.patch("/recommendations/{rec_id}")
def update_recommendation(project_id: str, rec_id: str, body: RecommendationUpdate, user: dict = Depends(get_current_user)):
    project = workspace.get_project(user["_id"], project_id)
    rec = dbm.find_one(dbm.RECOMMENDATIONS, {"_id": rec_id, "project_id": project["_id"]})
    if rec is None:
        raise NotFoundError("Recommendation not found.")
    dbm.update(dbm.RECOMMENDATIONS, {"_id": rec_id}, {"status": body.status})
    return dbm.serialize(dbm.get(dbm.RECOMMENDATIONS, rec_id))


@router.get("/context")
def learning_context(project_id: str, user: dict = Depends(get_current_user)):
    project = workspace.get_project(user["_id"], project_id)
    g = growth_for_project(project["_id"])
    return {**ctx_mod.dashboard_context(user["_id"], project, g), "prompt_block": ctx_mod.compose(user["_id"], project, g)}


@router.post("/context/notes", status_code=status.HTTP_201_CREATED)
def add_note(project_id: str, body: NoteCreate, user: dict = Depends(get_current_user)):
    project = workspace.get_project(user["_id"], project_id)
    return dbm.serialize(ctx_mod.add_note(user["_id"], project["_id"], body.kind, body.content, source="user"))


@router.delete("/context/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(project_id: str, note_id: str, user: dict = Depends(get_current_user)):
    workspace.get_project(user["_id"], project_id)
    dbm.get_db()[dbm.LEARNER_NOTES].update_one({"_id": note_id, "user_id": user["_id"]}, {"$set": {"active": False}})
