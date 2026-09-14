from fastapi import APIRouter, Depends, HTTPException, status

from app.core import db as dbm
from app.core.auth import require_admin
from app.schemas import EvalStart
from app.services.admin import service as admin
from app.services.evals import runner
from app.services.prompts.registry import PROMPTS

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/overview")
def overview():
    return admin.overview()


@router.get("/users")
def users(search: str | None = None, limit: int = 100):
    return admin.users(limit=min(limit, 500), search=search)


@router.get("/users/{user_id}")
def user_detail(user_id: str):
    detail = admin.user_detail(user_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    return detail


@router.get("/spaces")
def spaces():
    return admin.spaces()


@router.get("/projects")
def projects():
    return admin.projects()


@router.get("/activity")
def activity(user_id: str | None = None, space_id: str | None = None, project_id: str | None = None, event_type: str | None = None, days: int | None = None, limit: int = 100):
    return admin.activity(user_id=user_id, space_id=space_id, project_id=project_id, event_type=event_type, days=days, limit=min(limit, 500))


@router.get("/learning")
def learning():
    return admin.learning_analytics()


@router.get("/ai")
def ai(days: int = 14):
    return admin.ai_usage(days=min(days, 90))


@router.get("/ai/requests/{request_id}")
def ai_request(request_id: str):
    detail = admin.ai_request_detail(request_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found.")
    return detail


@router.get("/prompts")
def prompts():
    return [{"name": p.name, "version": p.version, "responsibility": p.responsibility} for p in PROMPTS.values()]


@router.get("/health")
def health():
    return admin.system_health()


@router.get("/evals")
def evals():
    return admin.eval_runs()


@router.get("/evals/{run_id}")
def eval_detail(run_id: str):
    if dbm.get(dbm.EVAL_RUNS, run_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found.")
    return runner.run_detail(run_id)


@router.post("/evals", status_code=status.HTTP_201_CREATED)
def run_eval(body: EvalStart, user: dict = Depends(require_admin)):
    project = dbm.get(dbm.PROJECTS, body.project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found.")
    owner = dbm.get(dbm.USERS, project["user_id"]) or user
    return runner.run_suite(project, owner, body.suite)
