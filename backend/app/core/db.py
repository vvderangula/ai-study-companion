"""MongoDB connection, collection names, indexes and small document helpers.

Documents are plain dicts. Every document has a string ``_id`` (uuid hex),
``created_at`` and ``updated_at``. Project-scoped collections carry
``project_id`` and ``user_id`` so isolation is one filter clause.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database

from app.core.config import settings

# Collection names
USERS = "users"
SPACES = "spaces"
PROJECTS = "projects"
MATERIALS = "materials"
CHUNKS = "chunks"
CONCEPTS = "concepts"
MASTERY = "mastery"
MASTERY_HISTORY = "mastery_history"
CONVERSATIONS = "conversations"
MESSAGES = "messages"
QUIZ_SESSIONS = "quiz_sessions"
QUIZ_QUESTIONS = "quiz_questions"
LEARNER_NOTES = "learner_notes"
RECOMMENDATIONS = "recommendations"
ACTIVITY = "activity_events"
AI_REQUESTS = "ai_requests"
JOBS = "jobs"
EVAL_RUNS = "eval_runs"
EVAL_RESULTS = "eval_results"

_client: MongoClient | None = None
_db: Database | None = None


def new_id() -> str:
    return uuid.uuid4().hex


def now() -> datetime:
    return datetime.now(timezone.utc)


def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(settings.mongo_url, uuidRepresentation="standard", serverSelectionTimeoutMS=5000, tz_aware=True)
    return _client


def get_db() -> Database:
    global _db
    if _db is None:
        _db = get_client()[settings.mongo_db]
    return _db


def set_db(db: Database | None) -> None:
    """Test hook: inject a mongomock database."""
    global _db
    _db = db


def init_db() -> None:
    db = get_db()
    db[USERS].create_index("email", unique=True)
    db[SPACES].create_index([("user_id", ASCENDING), ("updated_at", DESCENDING)])
    db[PROJECTS].create_index([("user_id", ASCENDING), ("last_accessed_at", DESCENDING)])
    db[PROJECTS].create_index("space_id")
    db[MATERIALS].create_index([("project_id", ASCENDING), ("created_at", DESCENDING)])
    db[CHUNKS].create_index([("project_id", ASCENDING), ("material_id", ASCENDING), ("ordinal", ASCENDING)])
    db[CONCEPTS].create_index([("project_id", ASCENDING), ("slug", ASCENDING)], unique=True)
    db[MASTERY].create_index("concept_id", unique=True)
    db[MASTERY].create_index("project_id")
    db[MASTERY_HISTORY].create_index([("concept_id", ASCENDING), ("created_at", ASCENDING)])
    db[MASTERY_HISTORY].create_index([("project_id", ASCENDING), ("created_at", ASCENDING)])
    db[MASTERY_HISTORY].create_index([("concept_id", ASCENDING), ("source_ref", ASCENDING)])
    db[CONVERSATIONS].create_index([("project_id", ASCENDING), ("updated_at", DESCENDING)])
    db[MESSAGES].create_index([("conversation_id", ASCENDING), ("created_at", ASCENDING)])
    db[QUIZ_SESSIONS].create_index([("project_id", ASCENDING), ("created_at", DESCENDING)])
    db[QUIZ_SESSIONS].create_index("idempotency_key", unique=True, sparse=True)
    db[QUIZ_QUESTIONS].create_index([("session_id", ASCENDING), ("ordinal", ASCENDING)])
    db[QUIZ_QUESTIONS].create_index([("project_id", ASCENDING), ("answered_at", DESCENDING)])
    db[LEARNER_NOTES].create_index([("user_id", ASCENDING), ("project_id", ASCENDING), ("active", ASCENDING)])
    db[LEARNER_NOTES].create_index("dedupe_key")
    db[RECOMMENDATIONS].create_index([("project_id", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)])
    db[ACTIVITY].create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
    db[ACTIVITY].create_index([("project_id", ASCENDING), ("created_at", DESCENDING)])
    db[ACTIVITY].create_index([("event_type", ASCENDING), ("created_at", DESCENDING)])
    db[ACTIVITY].create_index("dedupe_key", unique=True, sparse=True)
    db[AI_REQUESTS].create_index([("created_at", DESCENDING)])
    db[AI_REQUESTS].create_index([("feature", ASCENDING), ("created_at", DESCENDING)])
    db[AI_REQUESTS].create_index("project_id")
    db[JOBS].create_index([("status", ASCENDING), ("created_at", DESCENDING)])
    db[JOBS].create_index("dedupe_key", sparse=True)
    db[EVAL_RUNS].create_index([("created_at", DESCENDING)])
    db[EVAL_RESULTS].create_index("run_id")


# --------------------------------------------------------------------------- helpers


def insert(collection: str, doc: dict[str, Any]) -> dict[str, Any]:
    doc.setdefault("_id", new_id())
    ts = now()
    doc.setdefault("created_at", ts)
    doc.setdefault("updated_at", ts)
    # sparse unique indexes still index explicit nulls: omit optional unique keys when unset
    for key in ("dedupe_key", "idempotency_key"):
        if key in doc and doc[key] is None:
            del doc[key]
    get_db()[collection].insert_one(doc)
    return doc


def update(collection: str, filter_: dict[str, Any], fields: dict[str, Any], *, push: dict | None = None, inc: dict | None = None) -> None:
    ops: dict[str, Any] = {"$set": {**fields, "updated_at": now()}}
    if push:
        ops["$push"] = push
    if inc:
        ops["$inc"] = inc
    get_db()[collection].update_one(filter_, ops)


def find_one(collection: str, filter_: dict[str, Any]) -> dict[str, Any] | None:
    return get_db()[collection].find_one(filter_)


def get(collection: str, id_: str) -> dict[str, Any] | None:
    return get_db()[collection].find_one({"_id": id_})


def serialize(doc: dict[str, Any] | None, *, drop: tuple[str, ...] = ()) -> dict[str, Any] | None:
    """Rename _id -> id, drop private/heavy fields, make datetimes JSON-friendly."""
    if doc is None:
        return None
    out: dict[str, Any] = {}
    for key, value in doc.items():
        if key in drop:
            continue
        if key == "_id":
            out["id"] = value
        elif isinstance(value, datetime):
            out[key] = value.isoformat()
        else:
            out[key] = value
    return out
