"""Adaptive quiz: concept selection, question generation, grading, mastery update.

Selection is not "wrong -> easier / right -> harder". Each concept gets a priority
from low mastery, importance, recent mistakes and low confidence, minus penalties
for concepts already asked in this session. Difficulty comes from the mastery band
and is nudged by the last result on that concept. Open-ended questions are graded
by a rubric-based structured evaluation that yields feedback, not just a score.
"""

from __future__ import annotations

import logging
import random

from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from app.core import db as dbm
from app.core.errors import AIUnavailableError, ConflictError, NotFoundError, NotReadyError, ValidationFailed
from app.models import QuizQuestion, QuizSession
from app.services import events
from app.services.ai.provider import AIClient, CallContext
from app.services.learning import context as ctx_mod
from app.services.learning.mastery import ConceptGrowth, apply_evidence, growth_for_project
from app.services.prompts.registry import QUIZ_GENERATE, QUIZ_GRADE_OPEN
from app.services.retrieval import chunks_for_pages, format_evidence, search

logger = logging.getLogger(__name__)

DIFFICULTIES = ["easy", "medium", "hard"]


# --------------------------------------------------------------------------- selection


def select_concept(growth: list[ConceptGrowth], asked: list[dict], focus_concept_id: str | None = None, rng: random.Random | None = None) -> ConceptGrowth:
    rng = rng or random.Random()
    if focus_concept_id:
        match = next((g for g in growth if g.concept_id == focus_concept_id), None)
        if match and sum(1 for q in asked if q.get("concept_id") == focus_concept_id) < 3:
            return match
    counts: dict[str, int] = {}
    for q in asked:
        counts[q.get("concept_id")] = counts.get(q.get("concept_id"), 0) + 1
    last_two = [q.get("concept_id") for q in asked[-2:]]
    scored = []
    for g in growth:
        priority = (1.0 - g.score) * (0.5 + g.importance)
        priority += 0.25 if g.last_result == "incorrect" else 0.0
        priority += 0.2 * (1.0 - g.confidence)
        priority -= 0.3 if g.concept_id in last_two else 0.0
        priority -= 0.15 * counts.get(g.concept_id, 0)
        scored.append((priority, g))
    scored.sort(key=lambda t: -t[0])
    top = scored[:3]
    weights = [max(0.05, p) for p, _ in top]
    return rng.choices([g for _, g in top], weights=weights, k=1)[0]


def select_difficulty(g: ConceptGrowth, asked: list[dict]) -> str:
    if g.attempts == 0:
        base = "medium" if g.importance >= 0.7 else "easy"
    elif g.score < 0.4:
        base = "easy"
    elif g.score < 0.7:
        base = "medium"
    else:
        base = "hard"
    last = next((q for q in reversed(asked) if q.get("concept_id") == g.concept_id and q.get("is_correct") is not None), None)
    if last:
        idx = DIFFICULTIES.index(base)
        if last["is_correct"] and last["difficulty"] == base:
            idx = min(2, idx + 1)
        elif not last["is_correct"] and DIFFICULTIES.index(last["difficulty"]) < idx:
            idx = DIFFICULTIES.index(last["difficulty"])
        base = DIFFICULTIES[idx]
    return base


def select_kind(ordinal: int, target: int, g: ConceptGrowth) -> str:
    # at least one open question per quiz; more when the learner already recalls facts well
    if ordinal == min(2, target - 1):
        return "open"
    if g.score >= 0.6 and ordinal % 2 == 1:
        return "open"
    return "mcq"


# --------------------------------------------------------------------------- generation


class GeneratedQuestion(BaseModel):
    question: str
    options: list[str] = []
    correct_option: int | None = None
    reference_answer: str | None = None
    rubric: list[str] = []
    explanation: str = ""
    source_pages: list[int] = []


def _evidence_for(project_id: str, g: ConceptGrowth):
    hits = []
    if g.source_material_id and g.source_pages:
        hits = chunks_for_pages(project_id, g.source_material_id, g.source_pages[:4], limit=4)
    if len(hits) < 3:
        extra = search(project_id, f"{g.name}: {g.description}", top_k=4).hits
        seen = {h.chunk_id for h in hits}
        hits += [h for h in extra if h.chunk_id not in seen]
    return hits[:5]


def generate_question(ai: AIClient, project: dict, user_id: str, session: dict, g: ConceptGrowth, ordinal: int, asked: list[dict]) -> dict:
    difficulty = select_difficulty(g, asked)
    kind = select_kind(ordinal, session["target_questions"], g)
    hits = _evidence_for(project["_id"], g)
    if not hits:
        raise NotReadyError("No processed material covers this concept yet.")
    learner_context = ctx_mod.compose(user_id, project)
    avoid = "; ".join(q["prompt"][:80] for q in asked[-6:]) or "none"
    system = QUIZ_GENERATE.render(concept_name=g.name, concept_description=g.description, kind=kind, difficulty=difficulty, learner_context=learner_context[:800], avoid=avoid, evidence=format_evidence(hits))
    parsed, req_id = ai.generate_structured(
        CallContext(feature="quiz_generate", user_id=user_id, project_id=project["_id"], prompt_name=QUIZ_GENERATE.name, prompt_version=QUIZ_GENERATE.version, retrieval={"hits": [{"chunk_id": h.chunk_id, "page": h.page_start} for h in hits]}),
        GeneratedQuestion, system=system, messages=[{"role": "user", "content": f"Write one {difficulty} {kind} question."}], max_tokens=900, temperature=0.4,
    )
    # --- validate the model output before persisting ---
    if kind == "mcq":
        options = [o.strip() for o in parsed.options if o and o.strip()]
        if len(options) != 4 or parsed.correct_option is None or not 0 <= parsed.correct_option < 4 or len(set(o.lower() for o in options)) != 4:
            raise AIUnavailableError("Generated question failed validation.", code="ai_invalid_output")
    else:
        options = []
        if not parsed.reference_answer or len(parsed.rubric) < 1:
            raise AIUnavailableError("Generated open question failed validation.", code="ai_invalid_output")
    if len(parsed.question.strip()) < 10:
        raise AIUnavailableError("Generated question too short.", code="ai_invalid_output")

    doc = QuizQuestion(
        session_id=session["_id"], project_id=project["_id"], user_id=user_id, concept_id=g.concept_id, concept_name=g.name, ordinal=ordinal, kind=kind, difficulty=difficulty,
        prompt=parsed.question.strip(), options=options, correct_option=parsed.correct_option if kind == "mcq" else None, reference_answer=parsed.reference_answer if kind == "open" else None,
        rubric=[r for r in parsed.rubric if r.strip()][:5] if kind == "open" else [], explanation=parsed.explanation.strip(),
        source_chunk_ids=[h.chunk_id for h in hits], source_pages=sorted({p for p in parsed.source_pages if isinstance(p, int)} or {h.page_start for h in hits})[:6], source_material=hits[0].material_title, ai_request_id=req_id,
    ).to_doc()
    dbm.insert(dbm.QUIZ_QUESTIONS, doc)
    return doc


def _next_question(ai: AIClient, project: dict, user_id: str, session: dict) -> dict:
    growth = growth_for_project(project["_id"])
    if not growth:
        raise NotReadyError("This project has no concepts yet. Upload and process a material first.")
    asked = list(dbm.get_db()[dbm.QUIZ_QUESTIONS].find({"session_id": session["_id"]}).sort("ordinal", 1))
    focus = (session.get("focus_concept_ids") or [None])[0]
    last_error: Exception | None = None
    for attempt in range(2):
        g = select_concept(growth, asked, focus, random.Random(f"{session['_id']}:{len(asked)}:{attempt}"))
        try:
            return generate_question(ai, project, user_id, session, g, len(asked), asked)
        except AIUnavailableError as exc:
            last_error = exc
            logger.warning("question generation attempt %s failed: %s", attempt + 1, exc)
    raise last_error or AIUnavailableError("Could not generate a question.")


# --------------------------------------------------------------------------- session lifecycle


def start_session(project: dict, user: dict, *, target_questions: int = 5, focus_concept_id: str | None = None, idempotency_key: str | None = None) -> dict:
    if not dbm.get_db()[dbm.MATERIALS].find_one({"project_id": project["_id"], "status": "ready"}):
        raise NotReadyError("Add and process at least one material before taking a quiz.")
    if idempotency_key:
        existing = dbm.find_one(dbm.QUIZ_SESSIONS, {"idempotency_key": idempotency_key})
        if existing:
            return existing
    doc = QuizSession(project_id=project["_id"], user_id=user["_id"], target_questions=max(3, min(10, target_questions)), focus_concept_ids=[focus_concept_id] if focus_concept_id else [], idempotency_key=idempotency_key).to_doc()
    try:
        dbm.insert(dbm.QUIZ_SESSIONS, doc)
    except DuplicateKeyError:
        return dbm.find_one(dbm.QUIZ_SESSIONS, {"idempotency_key": idempotency_key})
    events.emit(events.Event(type=events.QUIZ_STARTED, user_id=user["_id"], project_id=project["_id"], ref_id=doc["_id"], ref_title=f"Quiz ({doc['target_questions']} questions)"))
    return doc


def current_question(session: dict) -> dict | None:
    return dbm.get_db()[dbm.QUIZ_QUESTIONS].find_one({"session_id": session["_id"], "answered_at": None}, sort=[("ordinal", 1)])


def ensure_question(project: dict, user: dict, session: dict) -> dict | None:
    """Return the pending question, generating it if needed. None when the session is complete."""
    if session["status"] != "active":
        return None
    pending = current_question(session)
    if pending:
        return pending
    if session["answered"] >= session["target_questions"]:
        return None
    return _next_question(AIClient(), project, user["_id"], session)


# --------------------------------------------------------------------------- grading


class OpenGrade(BaseModel):
    score: float
    is_correct: bool
    covered_points: list[str] = []
    missing_points: list[str] = []
    accuracy_issues: list[str] = []
    feedback: str


def _grade_open(ai: AIClient, project: dict, user_id: str, question: dict, answer: str) -> OpenGrade:
    hits = chunks_for_pages(project["_id"], next(iter(dbm.get_db()[dbm.CHUNKS].find({"_id": {"$in": question["source_chunk_ids"]}}, {"material_id": 1})), {}).get("material_id", ""), question.get("source_pages", []), limit=4) if question.get("source_chunk_ids") else []
    system = QUIZ_GRADE_OPEN.render(concept_name=question.get("concept_name") or "", question=question["prompt"], reference_answer=question.get("reference_answer") or "", rubric="; ".join(question.get("rubric", [])), evidence=format_evidence(hits) if hits else "(see reference answer)", answer=answer[:3000])
    parsed, _ = ai.generate_structured(
        CallContext(feature="quiz_grade", user_id=user_id, project_id=project["_id"], prompt_name=QUIZ_GRADE_OPEN.name, prompt_version=QUIZ_GRADE_OPEN.version),
        OpenGrade, system=system, messages=[{"role": "user", "content": "Grade the answer."}], max_tokens=700,
    )
    parsed.score = max(0.0, min(1.0, parsed.score))
    parsed.is_correct = parsed.score >= 0.7
    return parsed


def submit_answer(project: dict, user: dict, session: dict, question_id: str, answer: str) -> dict:
    question = dbm.find_one(dbm.QUIZ_QUESTIONS, {"_id": question_id, "session_id": session["_id"]})
    if question is None:
        raise NotFoundError("Question not found in this quiz.")
    if question.get("answered_at"):
        raise ConflictError("This question was already answered.")
    if session["status"] != "active":
        raise ConflictError("This quiz is no longer active.")
    answer = (answer or "").strip()
    if not answer:
        raise ValidationFailed("An answer is required.")

    ai = AIClient()
    evaluation: dict = {}
    if question["kind"] == "mcq":
        try:
            choice = int(answer)
        except ValueError:
            raise ValidationFailed("Multiple-choice answers must be the option index.")
        if not 0 <= choice < len(question["options"]):
            raise ValidationFailed("Option index out of range.")
        is_correct = choice == question["correct_option"]
        score = 1.0 if is_correct else 0.0
        feedback = question.get("explanation") or ("Correct." if is_correct else f"The correct answer was: {question['options'][question['correct_option']]}.")
        if not is_correct:
            feedback = f"Not quite. The correct answer is \"{question['options'][question['correct_option']]}\". {question.get('explanation', '')}".strip()
        user_answer = str(choice)
    else:
        grade = _grade_open(ai, project, user["_id"], question, answer)
        is_correct, score, feedback = grade.is_correct, grade.score, grade.feedback
        evaluation = grade.model_dump()
        user_answer = answer

    dbm.update(dbm.QUIZ_QUESTIONS, {"_id": question_id}, {"answered_at": dbm.now(), "user_answer": user_answer, "is_correct": is_correct, "score": score, "feedback": feedback, "evaluation": evaluation})

    mastery_after = None
    if question.get("concept_id"):
        concept = dbm.get(dbm.CONCEPTS, question["concept_id"])
        if concept:
            m = apply_evidence(concept, result=score, difficulty=question["difficulty"], source="quiz_answer", source_ref=question_id)
            mastery_after = {"concept_id": concept["_id"], "concept_name": concept["name"], "score": m["score"], "confidence": m["confidence"], "attempts": m["attempts"]}
            events.emit(events.Event(type=events.MASTERY_UPDATED, user_id=user["_id"], project_id=project["_id"], ref_id=concept["_id"], ref_title=concept["name"], data={"score": m["score"]}, dedupe_key=f"mastery:{question_id}"))

    answered = session["answered"] + 1
    correct_count = session["correct"] + (1 if is_correct else 0)
    fields: dict = {"answered": answered, "correct": correct_count}
    completed = answered >= session["target_questions"]
    if completed:
        qs = list(dbm.get_db()[dbm.QUIZ_QUESTIONS].find({"session_id": session["_id"], "answered_at": {"$ne": None}}, {"score": 1}))
        fields.update({"status": "completed", "completed_at": dbm.now(), "score": round(sum(q.get("score") or 0 for q in qs) / max(1, len(qs)), 3)})
    dbm.update(dbm.QUIZ_SESSIONS, {"_id": session["_id"]}, fields)
    session = dbm.get(dbm.QUIZ_SESSIONS, session["_id"])
    events.emit(events.Event(type=events.QUESTION_ANSWERED, user_id=user["_id"], project_id=project["_id"], ref_id=question_id, data={"correct": is_correct, "score": score}, dedupe_key=f"answered:{question_id}"))
    if completed:
        events.emit(events.Event(type=events.QUIZ_COMPLETED, user_id=user["_id"], project_id=project["_id"], ref_id=session["_id"], ref_title=f"Quiz score {int(session['score'] * 100)}%", data={"score": session["score"], "answered": answered, "correct": correct_count}, dedupe_key=f"quiz_completed:{session['_id']}"))

    next_q = None
    if not completed:
        try:
            next_q = _next_question(ai, project, user["_id"], session)
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not pre-generate next question: %s", exc)
    return {
        "question_id": question_id, "is_correct": is_correct, "score": score, "feedback": feedback, "evaluation": evaluation,
        "correct_option": question.get("correct_option"), "reference_answer": question.get("reference_answer"), "explanation": question.get("explanation"),
        "mastery": mastery_after, "session": dbm.serialize(session), "completed": completed, "next_question": public_question(next_q) if next_q else None,
    }


def public_question(q: dict | None) -> dict | None:
    """Question payload without the answer key."""
    if q is None:
        return None
    return dbm.serialize({k: v for k, v in q.items() if k not in ("correct_option", "reference_answer", "rubric", "explanation", "evaluation", "source_chunk_ids")})


def session_summary(session: dict) -> dict:
    qs = list(dbm.get_db()[dbm.QUIZ_QUESTIONS].find({"session_id": session["_id"]}).sort("ordinal", 1))
    return {"session": dbm.serialize(session), "questions": [dbm.serialize({k: v for k, v in q.items() if k != "source_chunk_ids"}) for q in qs]}
