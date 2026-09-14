"""Lightweight background work without an external queue.

Jobs run on an in-process thread pool (or inline in tests). Each job has a
``jobs`` document recording state, stage, attempts and errors; a dedupe key so
the same work isn't queued twice concurrently; and bounded retries with backoff.

Trade-off (documented): work is lost if the API process dies mid-job. For the
MVP that is acceptable; swapping ``enqueue`` to a real queue is a one-file change.
"""

from __future__ import annotations

import logging
import threading
import time
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from app.core import db as dbm
from app.core.config import settings
from app.models import Job

logger = logging.getLogger(__name__)

JobFn = Callable[[dict], dict | None]
_registry: dict[str, JobFn] = {}
_executor: ThreadPoolExecutor | None = None
_lock = threading.Lock()


def job(kind: str) -> Callable[[JobFn], JobFn]:
    def register(fn: JobFn) -> JobFn:
        _registry[kind] = fn
        return fn

    return register


def _pool() -> ThreadPoolExecutor:
    global _executor
    with _lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=settings.job_workers, thread_name_prefix="job")
    return _executor


def enqueue(kind: str, *, payload: dict | None = None, user_id: str | None = None, project_id: str | None = None, ref_id: str | None = None, dedupe_key: str | None = None) -> dict | None:
    """Create a job document and dispatch it. Returns None if a live duplicate exists."""
    coll = dbm.get_db()[dbm.JOBS]
    if dedupe_key and coll.find_one({"dedupe_key": dedupe_key, "status": {"$in": ["queued", "running"]}}):
        return None
    doc = Job(kind=kind, payload=payload or {}, user_id=user_id, project_id=project_id, ref_id=ref_id, dedupe_key=dedupe_key, max_attempts=settings.job_max_attempts).to_doc()
    dbm.insert(dbm.JOBS, doc)
    if settings.job_backend == "inline":
        run_job(doc["_id"])
    else:
        _pool().submit(run_job, doc["_id"])
    return dbm.get(dbm.JOBS, doc["_id"])


def run_job(job_id: str) -> None:
    coll = dbm.get_db()[dbm.JOBS]
    row = coll.find_one({"_id": job_id})
    if row is None or row["status"] == "completed":
        return
    fn = _registry.get(row["kind"])
    if fn is None:
        dbm.update(dbm.JOBS, {"_id": job_id}, {"status": "failed", "error": f"unknown job kind {row['kind']}"})
        return

    while True:
        row = coll.find_one({"_id": job_id})
        attempt = row["attempts"] + 1
        started = dbm.now()
        dbm.update(dbm.JOBS, {"_id": job_id}, {"status": "running", "attempts": attempt, "started_at": started, "error": None})
        try:
            result = fn(row) or {}
            finished = dbm.now()
            dbm.update(dbm.JOBS, {"_id": job_id}, {"status": "completed", "result": result, "finished_at": finished, "duration_ms": int((finished - started).total_seconds() * 1000), "stage": None})
            return
        except Exception as exc:  # noqa: BLE001
            exhausted = attempt >= row["max_attempts"] or getattr(exc, "no_retry", False)
            finished = dbm.now()
            dbm.update(dbm.JOBS, {"_id": job_id}, {"status": "failed" if exhausted else "queued", "error": f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-1200:]}", "finished_at": finished, "duration_ms": int((finished - started).total_seconds() * 1000)})
            logger.error("job %s (%s) failed attempt %s/%s: %s", job_id, row["kind"], attempt, row["max_attempts"], exc)
            if exhausted:
                return
            time.sleep(0 if settings.job_backend == "inline" else min(30, 3 * attempt))


def set_stage(job_id: str, stage: str) -> None:
    dbm.update(dbm.JOBS, {"_id": job_id}, {"stage": stage})


def health() -> dict:
    coll = dbm.get_db()[dbm.JOBS]
    return {
        "queued": coll.count_documents({"status": "queued"}),
        "running": coll.count_documents({"status": "running"}),
        "completed": coll.count_documents({"status": "completed"}),
        "failed": coll.count_documents({"status": "failed"}),
        "backend": settings.job_backend,
    }
