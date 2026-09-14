from fastapi import APIRouter, Depends, status

from app.core import db as dbm
from app.core.auth import get_current_user
from app.core.errors import NotFoundError
from app.schemas import QuizAnswer, QuizStart
from app.services.learning import workspace
from app.services.quiz import service as quiz

router = APIRouter(prefix="/projects/{project_id}/quiz", tags=["quiz"])


def _session(project: dict, user: dict, session_id: str) -> dict:
    session = dbm.find_one(dbm.QUIZ_SESSIONS, {"_id": session_id, "project_id": project["_id"], "user_id": user["_id"]})
    if session is None:
        raise NotFoundError("Quiz session not found.")
    return session


@router.get("/sessions")
def list_sessions(project_id: str, user: dict = Depends(get_current_user)):
    project = workspace.get_project(user["_id"], project_id)
    rows = dbm.get_db()[dbm.QUIZ_SESSIONS].find({"project_id": project["_id"]}).sort("created_at", -1).limit(20)
    return [dbm.serialize(s) for s in rows]


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
def start(project_id: str, body: QuizStart, user: dict = Depends(get_current_user)):
    project = workspace.get_project(user["_id"], project_id)
    session = quiz.start_session(project, user, target_questions=body.question_count, focus_concept_id=body.focus_concept_id, idempotency_key=body.idempotency_key)
    question = quiz.ensure_question(project, user, session)
    return {"session": dbm.serialize(session), "question": quiz.public_question(question)}


@router.get("/sessions/{session_id}")
def get_session(project_id: str, session_id: str, user: dict = Depends(get_current_user)):
    project = workspace.get_project(user["_id"], project_id)
    session = _session(project, user, session_id)
    question = quiz.ensure_question(project, user, session) if session["status"] == "active" else None
    return {**quiz.session_summary(session), "question": quiz.public_question(question)}


@router.post("/sessions/{session_id}/answer")
def answer(project_id: str, session_id: str, body: QuizAnswer, user: dict = Depends(get_current_user)):
    project = workspace.get_project(user["_id"], project_id)
    session = _session(project, user, session_id)
    return quiz.submit_answer(project, user, session, body.question_id, body.answer)


@router.post("/sessions/{session_id}/abandon")
def abandon(project_id: str, session_id: str, user: dict = Depends(get_current_user)):
    project = workspace.get_project(user["_id"], project_id)
    session = _session(project, user, session_id)
    if session["status"] == "active":
        dbm.update(dbm.QUIZ_SESSIONS, {"_id": session_id}, {"status": "abandoned"})
    return dbm.serialize(dbm.get(dbm.QUIZ_SESSIONS, session_id))
