"""Learner-facing analytics and dashboards (home, space, project, global)."""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

from app.core import db as dbm
from app.services import events
from app.services.learning import context as ctx_mod
from app.services.learning import recommendations
from app.services.learning.mastery import growth_for_project, mastery_timeline, overall_mastery


def _day(dt) -> str:
    return dt.date().isoformat()


def _activity_series(query: dict, days: int = 14) -> list[dict]:
    cutoff = dbm.now() - timedelta(days=days)
    counts = Counter(_day(e["created_at"]) for e in dbm.get_db()[dbm.ACTIVITY].find({**query, "created_at": {"$gte": cutoff}, "event_type": {"$ne": events.PROJECT_ACCESSED}}, {"created_at": 1}))
    today = dbm.now().date()
    return [{"date": (today - timedelta(days=i)).isoformat(), "events": counts.get((today - timedelta(days=i)).isoformat(), 0)} for i in range(days - 1, -1, -1)]


def _recent_activity(query: dict, limit: int = 12) -> list[dict]:
    rows = dbm.get_db()[dbm.ACTIVITY].find({**query, "event_type": {"$in": events.USER_FACING_TYPES}}).sort("created_at", -1).limit(limit)
    return [{**dbm.serialize(r), "label": events.LABELS.get(r["event_type"], r["event_type"])} for r in rows]


def _counts(project_ids: list[str]) -> dict:
    db = dbm.get_db()
    act = db[dbm.ACTIVITY]
    q = {"project_id": {"$in": project_ids}}
    return {
        "tutor_questions": act.count_documents({**q, "event_type": events.TUTOR_QUESTION_ASKED}),
        "quiz_attempts": db[dbm.QUIZ_SESSIONS].count_documents({"project_id": {"$in": project_ids}}),
        "quizzes_completed": db[dbm.QUIZ_SESSIONS].count_documents({"project_id": {"$in": project_ids}, "status": "completed"}),
        "questions_answered": db[dbm.QUIZ_QUESTIONS].count_documents({"project_id": {"$in": project_ids}, "answered_at": {"$ne": None}}),
        "materials": db[dbm.MATERIALS].count_documents({"project_id": {"$in": project_ids}}),
        "material_interactions": act.count_documents({**q, "event_type": {"$in": [events.MATERIAL_UPLOADED, events.MATERIAL_PROCESSED]}}),
        "active_days": len({_day(e["created_at"]) for e in act.find({**q, "event_type": {"$ne": events.PROJECT_ACCESSED}}, {"created_at": 1})}),
    }


def _quiz_accuracy(project_ids: list[str]) -> float | None:
    qs = list(dbm.get_db()[dbm.QUIZ_QUESTIONS].find({"project_id": {"$in": project_ids}, "answered_at": {"$ne": None}}, {"score": 1}))
    return round(sum(q.get("score") or 0 for q in qs) / len(qs), 3) if qs else None


def _assessment_trend(project_ids: list[str], limit: int = 12) -> list[dict]:
    rows = dbm.get_db()[dbm.QUIZ_SESSIONS].find({"project_id": {"$in": project_ids}, "status": "completed"}).sort("completed_at", -1).limit(limit)
    return [{"date": _day(s["completed_at"]), "score": s.get("score"), "session_id": s["_id"]} for s in reversed(list(rows))]


def _ai_activity(project_ids: list[str] | None, user_id: str | None = None) -> dict:
    q: dict = {}
    if project_ids is not None:
        q["project_id"] = {"$in": project_ids}
    if user_id:
        q["user_id"] = user_id
    counts = Counter(r["feature"] for r in dbm.get_db()[dbm.AI_REQUESTS].find(q, {"feature": 1}))
    return {"tutor_interactions": counts.get("tutor", 0), "quiz_questions_generated": counts.get("quiz_generate", 0), "ai_evaluations": counts.get("quiz_grade", 0), "recommendations_generated": counts.get("recommend", 0), "total_requests": sum(counts.values())}


# --------------------------------------------------------------------------- project


def project_dashboard(user_id: str, project: dict) -> dict:
    pid = project["_id"]
    growth = growth_for_project(pid)
    counts = _counts([pid])
    rec = recommendations.current(pid)
    materials = list(dbm.get_db()[dbm.MATERIALS].find({"project_id": pid}, {"title": 1, "status": 1, "stage": 1, "page_count": 1}).sort("created_at", -1))
    assessed = [g for g in growth if g.attempts]
    return {
        "project": dbm.serialize(project),
        "progress": {
            "overall_mastery": overall_mastery(growth),
            "concepts_total": len(growth),
            "concepts_assessed": len(assessed),
            "concepts_strong": sum(1 for g in assessed if g.band == "strong"),
            "concepts_attention": sum(1 for g in assessed if g.trend == "needs_attention" or g.band == "weak"),
            "quiz_accuracy": _quiz_accuracy([pid]),
        },
        "concepts": [g.to_dict() for g in growth],
        "materials": [dbm.serialize(m) for m in materials],
        "recent_activity": _recent_activity({"project_id": pid}),
        "performance": {"assessment_trend": _assessment_trend([pid]), **counts},
        "continue_learning": _continue_target(project),
        "recommendation": dbm.serialize(rec),
        "learning_context": ctx_mod.dashboard_context(user_id, project, growth),
    }


def _continue_target(project: dict) -> dict:
    t = project.get("last_activity_type")
    ref = project.get("last_activity_ref")
    if t in (events.TUTOR_QUESTION_ASKED, events.TUTOR_INTERACTION_COMPLETED, events.CONVERSATION_STARTED):
        return {"tab": "tutor", "label": "Continue your tutor conversation", "ref_id": ref}
    if t in (events.QUIZ_STARTED, events.QUESTION_ANSWERED):
        session = dbm.get(dbm.QUIZ_SESSIONS, ref) if ref else None
        if session and session["status"] == "active":
            return {"tab": "quiz", "label": "Resume your quiz", "ref_id": ref}
        return {"tab": "quiz", "label": "Take another quiz", "ref_id": None}
    if t in (events.QUIZ_COMPLETED, events.MASTERY_UPDATED):
        return {"tab": "growth", "label": "Review your growth", "ref_id": None}
    if t in (events.MATERIAL_UPLOADED, events.MATERIAL_PROCESSED):
        return {"tab": "tutor", "label": "Start learning with the tutor", "ref_id": None}
    return {"tab": "materials", "label": "Add learning material", "ref_id": None}


def project_analytics(project: dict) -> dict:
    pid = project["_id"]
    growth = growth_for_project(pid)
    assessed = [g for g in growth if g.attempts]
    return {
        "activity": {**_counts([pid]), "activity_over_time": _activity_series({"project_id": pid})},
        "performance": {
            "quiz_accuracy": _quiz_accuracy([pid]),
            "current_mastery": overall_mastery(growth),
            "concepts_mastered": [g.name for g in assessed if g.band == "strong"],
            "concepts_attention": [g.name for g in assessed if g.band == "weak" or g.trend == "needs_attention"],
        },
        "growth": {"mastery_over_time": mastery_timeline(pid), "assessment_trend": _assessment_trend([pid]), "concepts": [g.to_dict() for g in growth]},
        "ai_activity": _ai_activity([pid]),
    }


# --------------------------------------------------------------------------- space / home / global


def _project_summary(project: dict) -> dict:
    growth = growth_for_project(project["_id"])
    assessed = [g for g in growth if g.attempts]
    return {
        **dbm.serialize(project),
        "overall_mastery": overall_mastery(growth),
        "concepts_total": len(growth),
        "concepts_attention": sum(1 for g in assessed if g.band == "weak" or g.trend == "needs_attention"),
        "materials": dbm.get_db()[dbm.MATERIALS].count_documents({"project_id": project["_id"]}),
        "attention_concepts": [g.name for g in assessed if g.band == "weak" or g.trend == "needs_attention"][:3],
    }


def space_dashboard(user_id: str, space: dict) -> dict:
    projects = list(dbm.get_db()[dbm.PROJECTS].find({"space_id": space["_id"], "user_id": user_id}).sort("last_accessed_at", -1))
    summaries = [_project_summary(p) for p in projects]
    with_mastery = [s for s in summaries if s["concepts_total"]]
    return {
        "space": dbm.serialize(space),
        "project_count": len(projects),
        "overall_progress": round(sum(s["overall_mastery"] for s in with_mastery) / len(with_mastery), 3) if with_mastery else 0.0,
        "projects": summaries,
        "recent_activity": _recent_activity({"space_id": space["_id"]}),
        "attention": [{"project": s["name"], "project_id": s["id"], "concepts": s["attention_concepts"]} for s in summaries if s["attention_concepts"]],
    }


def home(user: dict) -> dict:
    uid = user["_id"]
    projects = list(dbm.get_db()[dbm.PROJECTS].find({"user_id": uid}).sort("last_accessed_at", -1))
    summaries = [_project_summary(p) for p in projects[:6]]
    with_mastery = [s for s in summaries if s["concepts_total"]]
    recs = list(dbm.get_db()[dbm.RECOMMENDATIONS].find({"user_id": uid, "status": "active"}).sort("created_at", -1).limit(3))
    attention = []
    for p in projects[:6]:
        for g in growth_for_project(p["_id"]):
            if g.attempts and (g.band == "weak" or g.trend == "needs_attention"):
                attention.append({"project_id": p["_id"], "project": p["name"], **g.to_dict()})
    attention.sort(key=lambda a: a["score"])
    return {
        "continue_learning": ({**_continue_target(projects[0]), "project": dbm.serialize(projects[0])} if projects else None),
        "recent_projects": summaries,
        "overall_progress": round(sum(s["overall_mastery"] for s in with_mastery) / len(with_mastery), 3) if with_mastery else 0.0,
        "areas_to_improve": attention[:5],
        "recommendations": [dbm.serialize(r) for r in recs],
        "spaces": dbm.get_db()[dbm.SPACES].count_documents({"user_id": uid}),
        "projects": len(projects),
    }


def global_analytics(user: dict) -> dict:
    uid = user["_id"]
    db = dbm.get_db()
    projects = list(db[dbm.PROJECTS].find({"user_id": uid}, {"_id": 1, "name": 1}))
    pids = [p["_id"] for p in projects]
    all_growth = []
    per_project = []
    for p in projects:
        g = growth_for_project(p["_id"])
        all_growth.extend(g)
        per_project.append({"project_id": p["_id"], "name": p["name"], "mastery": overall_mastery(g), "concepts": len(g)})
    assessed = [g for g in all_growth if g.attempts]
    counts = _counts(pids) if pids else {}
    completed = list(db[dbm.QUIZ_SESSIONS].find({"user_id": uid, "status": "completed"}, {"score": 1}))
    return {
        "overall": {"total_activity": db[dbm.ACTIVITY].count_documents({"user_id": uid, "event_type": {"$ne": events.PROJECT_ACCESSED}}), "active_days": counts.get("active_days", 0), "spaces": db[dbm.SPACES].count_documents({"user_id": uid}), "projects": len(projects)},
        "performance": {
            "overall_mastery": overall_mastery(all_growth),
            "average_assessment": round(sum(s.get("score") or 0 for s in completed) / len(completed), 3) if completed else None,
            "concepts_improving": [g.name for g in assessed if g.trend == "improving"],
            "concepts_attention": [g.name for g in assessed if g.band == "weak" or g.trend == "needs_attention"],
            "per_project": per_project,
        },
        "ai_usage": {**_ai_activity(None, uid), "questions_asked": counts.get("tutor_questions", 0), "quiz_activity": counts.get("quiz_attempts", 0)},
        "trends": {"activity_over_time": _activity_series({"user_id": uid}, days=30), "assessment_trend": _assessment_trend(pids, limit=20) if pids else [], "mastery_over_time": _global_mastery_timeline(pids)},
    }


def _global_mastery_timeline(pids: list[str], days: int = 30) -> list[dict]:
    if not pids:
        return []
    cutoff = dbm.now() - timedelta(days=days)
    latest: dict[str, float] = {}
    by_day: dict[str, float] = {}
    for row in dbm.get_db()[dbm.MASTERY_HISTORY].find({"project_id": {"$in": pids}, "created_at": {"$gte": cutoff}}).sort("created_at", 1):
        latest[row["concept_id"]] = row["score"]
        by_day[_day(row["created_at"])] = round(sum(latest.values()) / len(latest), 3)
    return [{"date": d, "mastery": v} for d, v in sorted(by_day.items())]
