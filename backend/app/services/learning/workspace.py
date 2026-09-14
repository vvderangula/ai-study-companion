"""Spaces, projects and materials: creation, ownership checks, uploads."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import UploadFile

from app.core import db as dbm
from app.core.config import settings
from app.core.errors import ConflictError, NotFoundError, ValidationFailed
from app.models import Material, Project, Space
from app.services import events
from app.services.materials.processing import file_hash

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


# --------------------------------------------------------------------------- spaces


def create_space(user: dict, name: str, description: str = "", color: str = "#f97316", icon: str = "📚") -> dict:
    doc = Space(user_id=user["_id"], name=name.strip(), description=description.strip(), color=color, icon=icon).to_doc()
    dbm.insert(dbm.SPACES, doc)
    events.emit(events.Event(type=events.SPACE_CREATED, user_id=user["_id"], space_id=doc["_id"], ref_id=doc["_id"], ref_title=doc["name"]))
    return doc


def list_spaces(user_id: str) -> list[dict]:
    return list(dbm.get_db()[dbm.SPACES].find({"user_id": user_id}).sort("updated_at", -1))


def get_space(user_id: str, space_id: str) -> dict:
    space = dbm.find_one(dbm.SPACES, {"_id": space_id, "user_id": user_id})
    if space is None:
        raise NotFoundError("Space not found.")
    return space


def update_space(user_id: str, space_id: str, fields: dict) -> dict:
    get_space(user_id, space_id)
    dbm.update(dbm.SPACES, {"_id": space_id}, {k: v for k, v in fields.items() if v is not None})
    return dbm.get(dbm.SPACES, space_id)


def delete_space(user_id: str, space_id: str) -> None:
    get_space(user_id, space_id)
    for p in dbm.get_db()[dbm.PROJECTS].find({"space_id": space_id}, {"_id": 1}):
        delete_project(user_id, p["_id"])
    dbm.get_db()[dbm.SPACES].delete_one({"_id": space_id})


# --------------------------------------------------------------------------- projects


def create_project(user: dict, space: dict, name: str, description: str = "", learning_goal: str = "") -> dict:
    doc = Project(space_id=space["_id"], user_id=user["_id"], name=name.strip(), description=description.strip(), learning_goal=learning_goal.strip()).to_doc()
    dbm.insert(dbm.PROJECTS, doc)
    dbm.update(dbm.SPACES, {"_id": space["_id"]}, {})
    events.emit(events.Event(type=events.PROJECT_CREATED, user_id=user["_id"], space_id=space["_id"], project_id=doc["_id"], ref_id=doc["_id"], ref_title=doc["name"]))
    return doc


def list_projects(user_id: str, space_id: str | None = None) -> list[dict]:
    query: dict = {"user_id": user_id}
    if space_id:
        query["space_id"] = space_id
    return list(dbm.get_db()[dbm.PROJECTS].find(query).sort("last_accessed_at", -1))


def get_project(user_id: str, project_id: str) -> dict:
    """Ownership check used by every project-scoped route."""
    project = dbm.find_one(dbm.PROJECTS, {"_id": project_id, "user_id": user_id})
    if project is None:
        raise NotFoundError("Project not found.")
    return project


def touch_project(user_id: str, project: dict) -> None:
    dbm.update(dbm.PROJECTS, {"_id": project["_id"]}, {"last_accessed_at": dbm.now()})
    events.emit(events.Event(type=events.PROJECT_ACCESSED, user_id=user_id, space_id=project["space_id"], project_id=project["_id"], ref_id=project["_id"], ref_title=project["name"], dedupe_key=f"access:{project['_id']}:{dbm.now().strftime('%Y%m%d%H')}"))


def update_project(user_id: str, project_id: str, fields: dict) -> dict:
    get_project(user_id, project_id)
    dbm.update(dbm.PROJECTS, {"_id": project_id}, {k: v for k, v in fields.items() if v is not None})
    return dbm.get(dbm.PROJECTS, project_id)


def delete_project(user_id: str, project_id: str) -> None:
    project = get_project(user_id, project_id)
    db = dbm.get_db()
    for m in db[dbm.MATERIALS].find({"project_id": project_id}, {"storage_path": 1}):
        Path(m["storage_path"]).unlink(missing_ok=True)
    for coll in (dbm.MATERIALS, dbm.CHUNKS, dbm.CONCEPTS, dbm.MASTERY, dbm.MASTERY_HISTORY, dbm.CONVERSATIONS, dbm.MESSAGES, dbm.QUIZ_SESSIONS, dbm.QUIZ_QUESTIONS, dbm.LEARNER_NOTES, dbm.RECOMMENDATIONS):
        db[coll].delete_many({"project_id": project_id})
    db[dbm.PROJECTS].delete_one({"_id": project["_id"]})


# --------------------------------------------------------------------------- materials


def _upload_root() -> Path:
    root = Path(settings.upload_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def upload_material(user: dict, project: dict, file: UploadFile, title: str | None = None) -> dict:
    name = file.filename or "document.pdf"
    if not name.lower().endswith(".pdf"):
        raise ValidationFailed("Only PDF files are supported in this prototype.")
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    material_id = dbm.new_id()
    dest = _upload_root() / user["_id"] / project["_id"]
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"{material_id}_{_SAFE.sub('_', name)[:80]}"
    head = file.file.read(5)
    if head != b"%PDF-":
        raise ValidationFailed("The file does not look like a valid PDF.")
    size = len(head)
    too_big = False
    with path.open("wb") as out:
        out.write(head)
        while chunk := file.file.read(1 << 20):
            size += len(chunk)
            if size > max_bytes:
                too_big = True
                break
            out.write(chunk)
    if too_big:
        path.unlink(missing_ok=True)
        raise ValidationFailed(f"File exceeds the {settings.max_upload_size_mb} MB limit.")

    digest = file_hash(path)
    duplicate = dbm.find_one(dbm.MATERIALS, {"project_id": project["_id"], "content_hash": digest})
    if duplicate:
        path.unlink(missing_ok=True)
        raise ConflictError(f"This file was already uploaded as \"{duplicate['title']}\".")

    doc = Material(_id=material_id, project_id=project["_id"], user_id=user["_id"], title=(title or name.rsplit(".", 1)[0]).strip()[:255], original_name=name[:255], storage_path=str(path), content_hash=digest, size_bytes=size).to_doc()
    dbm.insert(dbm.MATERIALS, doc)
    events.emit(events.Event(type=events.MATERIAL_UPLOADED, user_id=user["_id"], space_id=project["space_id"], project_id=project["_id"], ref_id=material_id, ref_title=doc["title"], data={"size": size}))
    return dbm.get(dbm.MATERIALS, material_id)


def list_materials(project_id: str) -> list[dict]:
    return list(dbm.get_db()[dbm.MATERIALS].find({"project_id": project_id}).sort("created_at", -1))


def get_material(project_id: str, material_id: str) -> dict:
    material = dbm.find_one(dbm.MATERIALS, {"_id": material_id, "project_id": project_id})
    if material is None:
        raise NotFoundError("Material not found.")
    return material


def retry_material(user: dict, project: dict, material_id: str) -> dict:
    material = get_material(project["_id"], material_id)
    if material["status"] not in ("failed", "queued"):
        raise ConflictError("Material is not in a retryable state.")
    dbm.update(dbm.MATERIALS, {"_id": material_id}, {"status": "queued", "error_message": None, "stage": None})
    events.emit(events.Event(type=events.MATERIAL_UPLOADED, user_id=user["_id"], space_id=project["space_id"], project_id=project["_id"], ref_id=material_id, ref_title=material["title"], data={"retry": True}))
    return dbm.get(dbm.MATERIALS, material_id)


def delete_material(project_id: str, material_id: str) -> None:
    material = get_material(project_id, material_id)
    Path(material["storage_path"]).unlink(missing_ok=True)
    db = dbm.get_db()
    db[dbm.CHUNKS].delete_many({"material_id": material_id})
    db[dbm.MATERIALS].delete_one({"_id": material_id})


def material_job(material: dict) -> dict | None:
    if not material.get("job_id"):
        return None
    job = dbm.get(dbm.JOBS, material["job_id"])
    return dbm.serialize(job, drop=("payload",)) if job else None
