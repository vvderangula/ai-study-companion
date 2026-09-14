"""Spaces and projects."""

from fastapi import APIRouter, Depends, status

from app.core import db as dbm
from app.core.auth import get_current_user
from app.schemas import ProjectCreate, ProjectUpdate, SpaceCreate, SpaceUpdate
from app.services.analytics import service as analytics
from app.services.learning import workspace

router = APIRouter(tags=["workspace"])


# --------------------------------------------------------------------------- spaces


@router.get("/spaces")
def list_spaces(user: dict = Depends(get_current_user)):
    spaces = workspace.list_spaces(user["_id"])
    counts = {s["_id"]: dbm.get_db()[dbm.PROJECTS].count_documents({"space_id": s["_id"]}) for s in spaces}
    return [{**dbm.serialize(s), "project_count": counts[s["_id"]]} for s in spaces]


@router.post("/spaces", status_code=status.HTTP_201_CREATED)
def create_space(body: SpaceCreate, user: dict = Depends(get_current_user)):
    return dbm.serialize(workspace.create_space(user, body.name, body.description, body.color, body.icon))


@router.get("/spaces/{space_id}")
def space_dashboard(space_id: str, user: dict = Depends(get_current_user)):
    return analytics.space_dashboard(user["_id"], workspace.get_space(user["_id"], space_id))


@router.patch("/spaces/{space_id}")
def update_space(space_id: str, body: SpaceUpdate, user: dict = Depends(get_current_user)):
    return dbm.serialize(workspace.update_space(user["_id"], space_id, body.model_dump()))


@router.delete("/spaces/{space_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_space(space_id: str, user: dict = Depends(get_current_user)):
    workspace.delete_space(user["_id"], space_id)


# --------------------------------------------------------------------------- projects


@router.get("/projects")
def list_projects(space_id: str | None = None, user: dict = Depends(get_current_user)):
    return [dbm.serialize(p) for p in workspace.list_projects(user["_id"], space_id)]


@router.post("/projects", status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectCreate, user: dict = Depends(get_current_user)):
    space = workspace.get_space(user["_id"], body.space_id)
    return dbm.serialize(workspace.create_project(user, space, body.name, body.description, body.learning_goal))


@router.get("/projects/{project_id}")
def project_dashboard(project_id: str, user: dict = Depends(get_current_user)):
    project = workspace.get_project(user["_id"], project_id)
    workspace.touch_project(user["_id"], project)
    return analytics.project_dashboard(user["_id"], project)


@router.patch("/projects/{project_id}")
def update_project(project_id: str, body: ProjectUpdate, user: dict = Depends(get_current_user)):
    return dbm.serialize(workspace.update_project(user["_id"], project_id, body.model_dump()))


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, user: dict = Depends(get_current_user)):
    workspace.delete_project(user["_id"], project_id)


@router.get("/projects/{project_id}/analytics")
def project_analytics(project_id: str, user: dict = Depends(get_current_user)):
    return analytics.project_analytics(workspace.get_project(user["_id"], project_id))
