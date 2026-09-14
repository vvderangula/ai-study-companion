"""Request/response schemas for the API."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    full_name: str
    email: str
    role: str


class SpaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    color: str = Field(default="#f97316", pattern=r"^#[0-9a-fA-F]{6}$")
    icon: str = Field(default="📚", max_length=10)


class SpaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    icon: str | None = Field(default=None, max_length=10)


class ProjectCreate(BaseModel):
    space_id: str = Field(min_length=32, max_length=32)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    learning_goal: str = Field(default="", max_length=1000)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    learning_goal: str | None = Field(default=None, max_length=1000)


class TutorAsk(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, min_length=32, max_length=32)


class QuizStart(BaseModel):
    question_count: int = Field(default=5, ge=3, le=10)
    focus_concept_id: str | None = Field(default=None, min_length=32, max_length=32)
    idempotency_key: str | None = Field(default=None, max_length=64)


class QuizAnswer(BaseModel):
    question_id: str = Field(min_length=32, max_length=32)
    answer: str = Field(min_length=1, max_length=5000)


class NoteCreate(BaseModel):
    kind: str = Field(pattern=r"^(goal|preference|strength|weakness)$")
    content: str = Field(min_length=3, max_length=400)


class GlobalNoteCreate(BaseModel):
    """User-level context. Concept-bound kinds stay project-scoped (see GLOBAL_KINDS)."""

    kind: str = Field(pattern=r"^(goal|preference)$")
    content: str = Field(min_length=3, max_length=400)


class RecommendationUpdate(BaseModel):
    status: str = Field(pattern=r"^(done|dismissed)$")


class EvalStart(BaseModel):
    project_id: str = Field(min_length=32, max_length=32)
    suite: str = Field(default="core", max_length=50)
