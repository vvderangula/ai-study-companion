"""Admin dashboard aggregations: users, activity, learning analytics, AI usage, health."""

from __future__ import annotations

import time
from collections import Counter, defaultdict
from datetime import timedelta

from app.core import db as dbm
from app.core.config import settings
from app.services import events, jobs
from app.services.ai.provider import provider_health
from app.services.learning.mastery import growth_for_project, overall_mastery


def _since(days: int):
    return dbm.now() - timedelta(days=days)


def overview() -> dict:
    db = dbm.get_db()
    ai = list(db[dbm.AI_REQUESTS].find({"created_at": {"$gte": _since(7)}}, {"status": 1, "latency_ms": 1, "cost_usd": 1}))
    errors = sum(1 for r in ai if r["status"] == "error")
    return {
        "users": {"total": db[dbm.USERS].count_documents({}), "active_7d": db[dbm.USERS].count_documents({"last_active_at": {"$gte": _since(7)}}), "active_1d": db[dbm.USERS].count_documents({"last_active_at": {"$gte": _since(1)}})},
        "spaces": db[dbm.SPACES].count_documents({}),
        "projects": db[dbm.PROJECTS].count_documents({}),
        "materials": {"total": db[dbm.MATERIALS].count_documents({}), "ready": db[dbm.MATERIALS].count_documents({"status": "ready"}), "failed": db[dbm.MATERIALS].count_documents({"status": "failed"})},
        "tutor_questions_7d": db[dbm.ACTIVITY].count_documents({"event_type": events.TUTOR_QUESTION_ASKED, "created_at": {"$gte": _since(7)}}),
        "quizzes_7d": db[dbm.QUIZ_SESSIONS].count_documents({"created_at": {"$gte": _since(7)}}),
        "activity_7d": db[dbm.ACTIVITY].count_documents({"created_at": {"$gte": _since(7)}, "event_type": {"$ne": events.PROJECT_ACCESSED}}),
        "ai": {"requests_7d": len(ai), "error_rate": round(errors / len(ai), 3) if ai else 0.0, "avg_latency_ms": int(sum(r["latency_ms"] for r in ai) / len(ai)) if ai else 0, "cost_7d": round(sum(r.get("cost_usd", 0) for r in ai), 4)},
        "jobs": jobs.health(),
        "activity_over_time": _series({"event_type": {"$ne": events.PROJECT_ACCESSED}}, 14),
    }


def _series(query: dict, days: int) -> list[dict]:
    counts = Counter(e["created_at"].date().isoformat() for e in dbm.get_db()[dbm.ACTIVITY].find({**query, "created_at": {"$gte": _since(days)}}, {"created_at": 1}))
    today = dbm.now().date()
    return [{"date": (today - timedelta(days=i)).isoformat(), "events": counts.get((today - timedelta(days=i)).isoformat(), 0)} for i in range(days - 1, -1, -1)]


def users(limit: int = 100, search: str | None = None) -> list[dict]:
    db = dbm.get_db()
    query = {"email": {"$regex": search, "$options": "i"}} if search else {}
    out = []
    for u in db[dbm.USERS].find(query, {"password_hash": 0}).sort("created_at", -1).limit(limit):
        pids = [p["_id"] for p in db[dbm.PROJECTS].find({"user_id": u["_id"]}, {"_id": 1})]
        mastery = [overall_mastery(growth_for_project(pid)) for pid in pids]
        mastery = [m for m in mastery if m]
        out.append({**dbm.serialize(u), "spaces": db[dbm.SPACES].count_documents({"user_id": u["_id"]}), "projects": len(pids), "activity": db[dbm.ACTIVITY].count_documents({"user_id": u["_id"], "event_type": {"$ne": events.PROJECT_ACCESSED}}), "overall_progress": round(sum(mastery) / len(mastery), 3) if mastery else 0.0})
    return out


def user_detail(user_id: str) -> dict | None:
    db = dbm.get_db()
    u = db[dbm.USERS].find_one({"_id": user_id}, {"password_hash": 0})
    if not u:
        return None
    spaces = [dbm.serialize(s) for s in db[dbm.SPACES].find({"user_id": user_id})]
    projects = []
    for p in db[dbm.PROJECTS].find({"user_id": user_id}).sort("last_accessed_at", -1):
        g = growth_for_project(p["_id"])
        projects.append({**dbm.serialize(p), "mastery": overall_mastery(g), "concepts": len(g), "materials": db[dbm.MATERIALS].count_documents({"project_id": p["_id"]})})
    completed = list(db[dbm.QUIZ_SESSIONS].find({"user_id": user_id, "status": "completed"}, {"score": 1}))
    ai = list(db[dbm.AI_REQUESTS].find({"user_id": user_id}, {"feature": 1, "cost_usd": 1, "input_tokens": 1, "output_tokens": 1}))
    timeline = [{**dbm.serialize(e), "label": events.LABELS.get(e["event_type"], e["event_type"])} for e in db[dbm.ACTIVITY].find({"user_id": user_id, "event_type": {"$ne": events.PROJECT_ACCESSED}}).sort("created_at", -1).limit(60)]
    return {
        "user": dbm.serialize(u),
        "spaces": spaces,
        "projects": projects,
        "assessment": {"quizzes_completed": len(completed), "average_score": round(sum(s.get("score") or 0 for s in completed) / len(completed), 3) if completed else None},
        "timeline": timeline,
        "usage": {"tutor": sum(1 for r in ai if r["feature"] == "tutor"), "quiz": sum(1 for r in ai if r["feature"] in ("quiz_generate", "quiz_grade")), "ai_requests": len(ai), "tokens": sum(r.get("input_tokens", 0) + r.get("output_tokens", 0) for r in ai), "cost_usd": round(sum(r.get("cost_usd", 0) for r in ai), 4), "sessions": len({e["created_at"][:10] for e in timeline})},
    }


def spaces(limit: int = 200) -> list[dict]:
    db = dbm.get_db()
    owners = {u["_id"]: u["email"] for u in db[dbm.USERS].find({}, {"email": 1})}
    out = []
    for s in db[dbm.SPACES].find().sort("updated_at", -1).limit(limit):
        last = db[dbm.ACTIVITY].find_one({"space_id": s["_id"]}, sort=[("created_at", -1)])
        out.append({**dbm.serialize(s), "owner": owners.get(s["user_id"]), "projects": db[dbm.PROJECTS].count_documents({"space_id": s["_id"]}), "activity": db[dbm.ACTIVITY].count_documents({"space_id": s["_id"]}), "last_activity": last["created_at"].isoformat() if last else None})
    return out


def projects(limit: int = 200) -> list[dict]:
    db = dbm.get_db()
    owners = {u["_id"]: u["email"] for u in db[dbm.USERS].find({}, {"email": 1})}
    space_names = {s["_id"]: s["name"] for s in db[dbm.SPACES].find({}, {"name": 1})}
    out = []
    for p in db[dbm.PROJECTS].find().sort("last_accessed_at", -1).limit(limit):
        pid = p["_id"]
        out.append({**dbm.serialize(p), "owner": owners.get(p["user_id"]), "space": space_names.get(p["space_id"]), "materials": db[dbm.MATERIALS].count_documents({"project_id": pid}), "tutor_activity": db[dbm.ACTIVITY].count_documents({"project_id": pid, "event_type": events.TUTOR_QUESTION_ASKED}), "quiz_activity": db[dbm.QUIZ_SESSIONS].count_documents({"project_id": pid}), "progress": overall_mastery(growth_for_project(pid))})
    return out


def activity(*, user_id: str | None = None, space_id: str | None = None, project_id: str | None = None, event_type: str | None = None, days: int | None = None, limit: int = 100) -> list[dict]:
    q: dict = {}
    if user_id:
        q["user_id"] = user_id
    if space_id:
        q["space_id"] = space_id
    if project_id:
        q["project_id"] = project_id
    if event_type:
        q["event_type"] = event_type
    if days:
        q["created_at"] = {"$gte": _since(days)}
    db = dbm.get_db()
    emails = {u["_id"]: u["email"] for u in db[dbm.USERS].find({}, {"email": 1})}
    return [{**dbm.serialize(e), "label": events.LABELS.get(e["event_type"], e["event_type"]), "user_email": emails.get(e.get("user_id"))} for e in db[dbm.ACTIVITY].find(q).sort("created_at", -1).limit(limit)]


def learning_analytics() -> dict:
    db = dbm.get_db()
    all_growth = []
    for p in db[dbm.PROJECTS].find({}, {"_id": 1}):
        all_growth.extend(growth_for_project(p["_id"]))
    assessed = [g for g in all_growth if g.attempts]
    feature_counts = Counter(e["event_type"] for e in db[dbm.ACTIVITY].find({"created_at": {"$gte": _since(30)}}, {"event_type": 1}))
    struggles = Counter(g.name for g in assessed if g.band == "weak")
    completed = list(db[dbm.QUIZ_SESSIONS].find({"status": "completed"}, {"score": 1}))
    return {
        "activity_over_time": _series({"event_type": {"$ne": events.PROJECT_ACCESSED}}, 30),
        "engagement": {"users_active_7d": db[dbm.USERS].count_documents({"last_active_at": {"$gte": _since(7)}}), "avg_events_per_active_user": round(db[dbm.ACTIVITY].count_documents({"created_at": {"$gte": _since(7)}}) / max(1, db[dbm.USERS].count_documents({"last_active_at": {"$gte": _since(7)}})), 1)},
        "assessment": {"quizzes_completed": len(completed), "average_score": round(sum(s.get("score") or 0 for s in completed) / len(completed), 3) if completed else None},
        "average_mastery": overall_mastery(all_growth),
        "features": [{"feature": events.LABELS.get(k, k), "count": v} for k, v in feature_counts.most_common(8)],
        "common_struggles": [{"concept": k, "count": v} for k, v in struggles.most_common(10)],
        "active_projects_7d": len(db[dbm.ACTIVITY].distinct("project_id", {"created_at": {"$gte": _since(7)}, "project_id": {"$ne": None}})),
    }


def ai_usage(days: int = 14) -> dict:
    rows = list(dbm.get_db()[dbm.AI_REQUESTS].find({"created_at": {"$gte": _since(days)}}))
    by_feature: dict[str, dict] = defaultdict(lambda: {"requests": 0, "errors": 0, "fallbacks": 0, "latency": 0, "cost": 0.0, "tokens_in": 0, "tokens_out": 0})
    by_model: Counter = Counter()
    by_provider: Counter = Counter()
    by_day: dict[str, dict] = defaultdict(lambda: {"requests": 0, "cost": 0.0, "errors": 0})
    latencies = []
    for r in rows:
        f = by_feature[r["feature"]]
        f["requests"] += 1
        f["errors"] += r["status"] == "error"
        f["fallbacks"] += r["status"] == "fallback"
        f["latency"] += r["latency_ms"]
        f["cost"] += r.get("cost_usd", 0)
        f["tokens_in"] += r.get("input_tokens", 0)
        f["tokens_out"] += r.get("output_tokens", 0)
        by_model[r["model"]] += 1
        by_provider[r["provider"]] += 1
        d = by_day[r["created_at"].date().isoformat()]
        d["requests"] += 1
        d["cost"] += r.get("cost_usd", 0)
        d["errors"] += r["status"] == "error"
        latencies.append(r["latency_ms"])
    latencies.sort()
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0
    return {
        "totals": {"requests": len(rows), "errors": sum(1 for r in rows if r["status"] == "error"), "fallbacks": sum(1 for r in rows if r["status"] == "fallback"), "cost_usd": round(sum(r.get("cost_usd", 0) for r in rows), 4), "tokens_in": sum(r.get("input_tokens", 0) for r in rows), "tokens_out": sum(r.get("output_tokens", 0) for r in rows), "avg_latency_ms": int(sum(latencies) / len(latencies)) if latencies else 0, "p95_latency_ms": p95},
        "by_feature": [{"feature": k, **v, "avg_latency_ms": int(v["latency"] / v["requests"]) if v["requests"] else 0, "cost": round(v["cost"], 4)} for k, v in sorted(by_feature.items(), key=lambda kv: -kv[1]["requests"])],
        "by_model": [{"model": k, "requests": v} for k, v in by_model.most_common()],
        "by_provider": [{"provider": k, "requests": v} for k, v in by_provider.most_common()],
        "by_day": [{"date": k, **{kk: (round(vv, 4) if isinstance(vv, float) else vv) for kk, vv in v.items()}} for k, v in sorted(by_day.items())],
        "recent_errors": [dbm.serialize(r, drop=("retrieval", "tool_calls")) for r in dbm.get_db()[dbm.AI_REQUESTS].find({"status": "error"}).sort("created_at", -1).limit(10)],
        "recent_requests": [dbm.serialize(r, drop=("retrieval", "tool_calls", "attempts")) for r in dbm.get_db()[dbm.AI_REQUESTS].find().sort("created_at", -1).limit(25)],
    }


def ai_request_detail(request_id: str) -> dict | None:
    return dbm.serialize(dbm.get(dbm.AI_REQUESTS, request_id))


def system_health() -> dict:
    db = dbm.get_db()
    started = time.perf_counter()
    try:
        db.command("ping")
        db_ok, db_ms = True, int((time.perf_counter() - started) * 1000)
    except Exception:  # noqa: BLE001
        db_ok, db_ms = False, None
    ai_recent = list(db[dbm.AI_REQUESTS].find({"created_at": {"$gte": _since(1)}}, {"status": 1, "latency_ms": 1, "provider": 1}))
    errors = sum(1 for r in ai_recent if r["status"] == "error")
    failed_jobs = [dbm.serialize(j, drop=("payload",)) for j in db[dbm.JOBS].find({"status": "failed"}).sort("created_at", -1).limit(10)]
    return {
        "api": {"ok": True, "environment": settings.environment},
        "database": {"ok": db_ok, "ping_ms": db_ms},
        "ai_providers": provider_health(),
        "ai_last_24h": {"requests": len(ai_recent), "errors": errors, "error_rate": round(errors / len(ai_recent), 3) if ai_recent else 0.0, "avg_latency_ms": int(sum(r["latency_ms"] for r in ai_recent) / len(ai_recent)) if ai_recent else 0},
        "background": {**jobs.health(), "backlog": db[dbm.MATERIALS].count_documents({"status": {"$in": ["queued", "processing"]}}), "recent_failures": failed_jobs},
        "embeddings": {"backend": settings.embedding_backend, "model": settings.embedding_model},
    }


def eval_runs(limit: int = 20) -> list[dict]:
    return [dbm.serialize(r) for r in dbm.get_db()[dbm.EVAL_RUNS].find().sort("created_at", -1).limit(limit)]
