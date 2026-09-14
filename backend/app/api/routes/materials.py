from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.core import db as dbm
from app.core.auth import get_current_user
from app.services.learning import workspace

router = APIRouter(prefix="/projects/{project_id}/materials", tags=["materials"])


def _view(material: dict) -> dict:
    return {**dbm.serialize(material, drop=("storage_path", "content_hash")), "job": workspace.material_job(material)}


@router.get("")
def list_materials(project_id: str, user: dict = Depends(get_current_user)):
    project = workspace.get_project(user["_id"], project_id)
    return [_view(m) for m in workspace.list_materials(project["_id"])]


@router.post("", status_code=status.HTTP_201_CREATED)
def upload_material(project_id: str, file: UploadFile = File(...), title: str | None = Form(default=None), user: dict = Depends(get_current_user)):
    project = workspace.get_project(user["_id"], project_id)
    return _view(workspace.upload_material(user, project, file, title))


@router.get("/{material_id}")
def get_material(project_id: str, material_id: str, user: dict = Depends(get_current_user)):
    project = workspace.get_project(user["_id"], project_id)
    return _view(workspace.get_material(project["_id"], material_id))


@router.post("/{material_id}/retry")
def retry_material(project_id: str, material_id: str, user: dict = Depends(get_current_user)):
    project = workspace.get_project(user["_id"], project_id)
    return _view(workspace.retry_material(user, project, material_id))


@router.delete("/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_material(project_id: str, material_id: str, user: dict = Depends(get_current_user)):
    project = workspace.get_project(user["_id"], project_id)
    workspace.delete_material(project["_id"], material_id)
