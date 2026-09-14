"""Document shapes for the MongoDB collections.

These Pydantic models document each collection's fields and are used to build
new documents with consistent defaults. Reads return plain dicts; writes go
through ``app.core.db.insert/update``. The ownership chain is
User -> Space -> Project -> everything else; every project-scoped document has
``project_id`` and ``user_id``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.db import new_id, now


class Doc(BaseModel):
    id: str = Field(default_factory=new_id, alias="_id")
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)

    model_config = {"populate_by_name": True}

    def to_doc(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)


class User(Doc):
    full_name: str
    email: str
    password_hash: str
    role: str = "learner"  # learner | admin
    last_active_at: datetime | None = None


class Space(Doc):
    user_id: str
    name: str
    description: str = ""
    color: str = "#f97316"
    icon: str = "📚"


class Project(Doc):
    space_id: str
    user_id: str
    name: str
    description: str = ""
    learning_goal: str = ""
    last_accessed_at: datetime = Field(default_factory=now)
    last_activity_type: str | None = None
    last_activity_ref: str | None = None


class Material(Doc):
    project_id: str
    user_id: str
    title: str
    original_name: str
    storage_path: str
    content_hash: str = ""
    size_bytes: int = 0
    mime_type: str = "application/pdf"
    status: str = "queued"  # queued | processing | ready | failed
    stage: str | None = None  # reading | structure | extracting | indexing
    error_message: str | None = None
    page_count: int = 0
    chunk_count: int = 0
    summary: str | None = None
    processed_at: datetime | None = None
    job_id: str | None = None


class Chunk(Doc):
    material_id: str
    project_id: str
    ordinal: int
    page_start: int
    page_end: int
    text: str
    kind: str = "text"  # text | table | ocr
    embedding: list[float] = Field(default_factory=list)


class Concept(Doc):
    project_id: str
    user_id: str
    name: str
    slug: str
    description: str = ""
    importance: float = 0.5
    source_material_id: str | None = None
    source_pages: list[int] = Field(default_factory=list)


class Mastery(Doc):
    concept_id: str
    project_id: str
    user_id: str
    score: float = 0.3
    confidence: float = 0.0
    attempts: int = 0
    correct: int = 0
    streak: int = 0
    last_result: str | None = None
    last_assessed_at: datetime | None = None


class MasteryHistory(Doc):
    concept_id: str
    project_id: str
    user_id: str
    score: float
    previous_score: float
    source: str  # quiz_answer | tutor_check
    source_ref: str | None = None


class Conversation(Doc):
    project_id: str
    user_id: str
    title: str = "New conversation"
    summary: str | None = None
    message_count: int = 0


class Message(Doc):
    conversation_id: str
    project_id: str
    role: str  # user | assistant
    content: str
    citations: list[dict] = Field(default_factory=list)
    tool_calls: list[dict] = Field(default_factory=list)
    grounded: bool | None = None
    ai_request_id: str | None = None


class QuizSession(Doc):
    project_id: str
    user_id: str
    status: str = "active"  # active | completed | abandoned
    target_questions: int = 5
    answered: int = 0
    correct: int = 0
    score: float | None = None
    focus_concept_ids: list[str] = Field(default_factory=list)
    completed_at: datetime | None = None
    idempotency_key: str | None = None


class QuizQuestion(Doc):
    session_id: str
    project_id: str
    user_id: str
    concept_id: str | None = None
    concept_name: str | None = None
    ordinal: int
    kind: str  # mcq | open
    difficulty: str  # easy | medium | hard
    prompt: str
    options: list[str] = Field(default_factory=list)
    correct_option: int | None = None
    reference_answer: str | None = None
    rubric: list[str] = Field(default_factory=list)
    explanation: str = ""
    source_chunk_ids: list[str] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)
    source_material: str | None = None
    answered_at: datetime | None = None
    user_answer: str | None = None
    is_correct: bool | None = None
    score: float | None = None
    feedback: str | None = None
    evaluation: dict = Field(default_factory=dict)
    ai_request_id: str | None = None


class LearnerNote(Doc):
    user_id: str
    project_id: str | None = None
    kind: str  # goal | strength | weakness | preference | tutor_note | pattern
    content: str
    concept_id: str | None = None
    weight: float = 1.0
    source: str = "system"  # user | system | tutor
    active: bool = True
    dedupe_key: str | None = None


class Recommendation(Doc):
    project_id: str
    user_id: str
    action: str  # quiz | tutor | review | upload
    title: str
    reason: str
    concept_ids: list[str] = Field(default_factory=list)
    concept_names: list[str] = Field(default_factory=list)
    payload: dict = Field(default_factory=dict)
    priority: int = 1
    trigger: str = "manual"
    status: str = "active"  # active | done | dismissed | superseded
    dedupe_key: str | None = None


class ActivityEvent(Doc):
    user_id: str | None = None
    space_id: str | None = None
    project_id: str | None = None
    event_type: str
    ref_id: str | None = None
    ref_title: str | None = None
    data: dict = Field(default_factory=dict)
    dedupe_key: str | None = None


class AIRequest(Doc):
    user_id: str | None = None
    project_id: str | None = None
    feature: str
    prompt_name: str | None = None
    prompt_version: str | None = None
    provider: str
    model: str
    tier: str = "primary"
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    status: str = "ok"  # ok | error | fallback
    error: str | None = None
    attempts: list[dict] = Field(default_factory=list)  # per-provider attempt log
    retrieval: dict = Field(default_factory=dict)
    tool_calls: list[dict] = Field(default_factory=list)
    request_id: str | None = None


class Job(Doc):
    kind: str
    dedupe_key: str | None = None
    user_id: str | None = None
    project_id: str | None = None
    ref_id: str | None = None
    status: str = "queued"  # queued | running | completed | failed
    stage: str | None = None
    attempts: int = 0
    max_attempts: int = 3
    error: str | None = None
    payload: dict = Field(default_factory=dict)
    result: dict = Field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None


class EvalRun(Doc):
    project_id: str | None = None
    user_id: str | None = None
    suite: str
    status: str = "running"
    total_cases: int = 0
    passed_cases: int = 0
    scores: dict = Field(default_factory=dict)
    baseline_run_id: str | None = None
    regressions: list[dict] = Field(default_factory=list)
    prompt_versions: dict = Field(default_factory=dict)
    model: str | None = None
    cost_usd: float = 0.0
    finished_at: datetime | None = None


class EvalResult(Doc):
    run_id: str
    case_id: str
    category: str
    input: dict = Field(default_factory=dict)
    output: dict = Field(default_factory=dict)
    scores: dict = Field(default_factory=dict)
    passed: bool = False
    notes: str | None = None
