"""Unit tests: mastery model, adaptive selection, jobs, structured output validation, chunking."""

import pytest
from pydantic import BaseModel

from app.core import db as dbm
from app.core.errors import AIUnavailableError
from app.services import jobs
from app.services.ai.provider import AIClient, CallContext, FakeProvider, RetryableAIError, extract_json
from app.services.learning.mastery import ConceptGrowth, compute_update
from app.services.materials.processing import Page, chunk_pages
from app.services.quiz.service import select_concept, select_difficulty


def test_mastery_update_direction_and_difficulty_weighting():
    up_hard, _ = compute_update(0.5, 0.0, 1.0, "hard")
    up_easy, _ = compute_update(0.5, 0.0, 1.0, "easy")
    assert up_hard > up_easy > 0.5
    down_easy, _ = compute_update(0.5, 0.0, 0.0, "easy")
    down_hard, _ = compute_update(0.5, 0.0, 0.0, "hard")
    assert down_easy < down_hard < 0.5
    # more evidence -> smaller steps
    big, conf = compute_update(0.5, 0.0, 1.0, "medium")
    small, _ = compute_update(0.5, 1.0, 1.0, "medium")
    assert (big - 0.5) > (small - 0.5)
    assert 0 < conf <= 1
    s, _ = compute_update(0.99, 0.0, 1.0, "hard")
    assert s <= 1.0


def _g(cid, score, importance=0.5, last=None, attempts=1, confidence=0.5):
    return ConceptGrowth(concept_id=cid, name=cid, description="", score=score, previous=score, delta=0, trend="stable", band="weak", attempts=attempts, confidence=confidence, last_result=last, importance=importance, source_pages=[], source_material_id=None)


def test_select_concept_prefers_weak_and_recent_mistakes():
    import random

    growth = [_g("strong", 0.9), _g("weak", 0.2), _g("mid", 0.6)]
    picks = [select_concept(growth, [], rng=random.Random(i)).concept_id for i in range(30)]
    assert picks.count("weak") > picks.count("strong")
    # avoid asking the same concept back-to-back
    asked = [{"concept_id": "weak"}, {"concept_id": "weak"}]
    picks2 = [select_concept(growth, asked, rng=random.Random(i)).concept_id for i in range(30)]
    assert picks2.count("weak") < picks.count("weak")
    # focus concept honoured
    assert select_concept(growth, [], focus_concept_id="mid").concept_id == "mid"


def test_select_difficulty_is_not_naive():
    g = _g("c", 0.3)
    assert select_difficulty(g, []) == "easy"
    g_hi = _g("c", 0.8)
    assert select_difficulty(g_hi, []) == "hard"
    # wrong answer keeps difficulty (does not simply drop); right at same level steps up
    mid = _g("c", 0.55)
    assert select_difficulty(mid, [{"concept_id": "c", "is_correct": True, "difficulty": "medium"}]) == "hard"
    assert select_difficulty(mid, [{"concept_id": "c", "is_correct": False, "difficulty": "medium"}]) == "medium"
    assert select_difficulty(_g("c", 0.0, attempts=0, importance=0.9), []) == "medium"


def test_chunking_keeps_page_numbers_and_overlap():
    pages = [Page(1, "para one. " * 60 + "\n\n" + "para two. " * 60), Page(2, "page two text. " * 80)]
    chunks = chunk_pages(pages, size=400, overlap=50)
    assert len(chunks) >= 3
    assert chunks[0].page_start == 1
    assert chunks[-1].page_end == 2
    assert all(len(c.text) <= 400 * 1.6 + 60 for c in chunks)


def test_extract_json_handles_fences():
    assert extract_json('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert extract_json('Sure! {"a": 1}') == '{"a": 1}'


class Out(BaseModel):
    value: int


def test_structured_output_falls_back_then_fails(fresh_db):
    bad = FakeProvider()
    bad.handlers["*"] = lambda kw: "not json at all"
    good = FakeProvider()
    good.name = "fake2"
    good.handlers["*"] = lambda kw: {"value": 7}
    client = AIClient([bad, good])
    parsed, req_id = client.generate_structured(CallContext(feature="t"), Out, system="x", messages=[{"role": "user", "content": "y"}])
    assert parsed.value == 7
    row = dbm.get(dbm.AI_REQUESTS, req_id)
    assert row["status"] == "fallback" and len(row["attempts"]) == 2 and row["attempts"][0]["ok"] is False

    only_bad = AIClient([bad])
    with pytest.raises(AIUnavailableError):
        only_bad.generate_structured(CallContext(feature="t"), Out, system="x", messages=[{"role": "user", "content": "y"}])
    assert dbm.get_db()[dbm.AI_REQUESTS].count_documents({"status": "error"}) == 1


def test_provider_fallback_on_retryable_error(fresh_db):
    class Down(FakeProvider):
        name = "down"

        def generate(self, **kw):
            raise RetryableAIError("down: 503")

    ok = FakeProvider()
    ok.handlers["*"] = lambda kw: "hello"
    result, req_id = AIClient([Down(), ok]).generate(CallContext(feature="t"), system="s", messages=[{"role": "user", "content": "u"}])
    assert result.text == "hello"
    assert dbm.get(dbm.AI_REQUESTS, req_id)["status"] == "fallback"


def test_job_retries_then_fails_and_dedupes(fresh_db, monkeypatch):
    calls = {"n": 0}

    @jobs.job("flaky")
    def flaky(job):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("boom")
        return {"ok": True}

    row = jobs.enqueue("flaky", dedupe_key="flaky:1")
    final = dbm.get(dbm.JOBS, row["_id"])
    assert final["status"] == "completed" and final["attempts"] == 3 and final["result"] == {"ok": True}

    calls["n"] = -10  # always fails
    row2 = jobs.enqueue("flaky", dedupe_key="flaky:2")
    final2 = dbm.get(dbm.JOBS, row2["_id"])
    assert final2["status"] == "failed" and final2["attempts"] == 3 and "boom" in final2["error"]

    # dedupe: a queued/running duplicate is not re-enqueued
    dbm.update(dbm.JOBS, {"_id": row2["_id"]}, {"status": "running"})
    assert jobs.enqueue("flaky", dedupe_key="flaky:2") is None


def test_tutor_errors_never_leak_provider_detail():
    """Learners must never read raw provider strings (keys, hosts, HTTP codes)."""
    from app.core.errors import AIUnavailableError, AppError
    from app.services.tutor.service import friendly_error

    raw = "All AI providers failed. gemini: no API key configured."
    leaky = ("API key", "provider", "gemini", "groq", "429", "http", "Traceback")

    for exc in (
        AIUnavailableError(raw, code="ai_not_configured"),
        AIUnavailableError(raw, code="ai_rate_limited"),
        AIUnavailableError(raw, code="ai_timeout"),
        AIUnavailableError(raw, code="ai_unavailable"),
        AIUnavailableError(raw),
        AppError("internal detail"),
        ValueError("boom"),
    ):
        msg = friendly_error(exc)
        assert msg, "a message is always shown"
        assert not any(w.lower() in msg.lower() for w in leaky), f"leaked: {msg}"
        assert any(s in msg.lower() for s in ("again", "contact")), f"no next step: {msg}"
