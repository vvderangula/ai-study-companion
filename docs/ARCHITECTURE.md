# Architecture

## 1. System diagram

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Browser · React + Vite + TypeScript                                          │
│   Home · Spaces · Project (Overview/Materials/Tutor/Quiz/Growth/Analytics)   │
│   Global analytics · Admin (overview/users/projects/activity/learning/AI/    │
│   evals/health)                                     JSON + Server-Sent Events│
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │ JWT bearer
┌───────────────────────────────▼──────────────────────────────────────────────┐
│ FastAPI · app/api/routes                                                     │
│   request-id middleware · JSON logs · AppError → HTTP mapping · validation   │
│   every project route: get_current_user → get_project(user, id) (ownership)  │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────────────────┐
│ Application services · app/services                                          │
│  ┌──────────────┐ ┌───────────────┐ ┌──────────────┐ ┌────────────────────┐ │
│  │ learning/    │ │ tutor/        │ │ quiz/        │ │ analytics/ admin/  │ │
│  │ workspace    │ │ retrieval →   │ │ select       │ │ dashboards,        │ │
│  │ mastery      │ │ context →     │ │ concept &    │ │ aggregations,      │ │
│  │ context      │ │ tools →       │ │ difficulty → │ │ health             │ │
│  │ recommend    │ │ stream answer │ │ generate →   │ │                    │ │
│  └──────────────┘ └───────────────┘ │ grade →      │ └────────────────────┘ │
│  ┌──────────────┐ ┌───────────────┐ │ mastery      │ ┌────────────────────┐ │
│  │ materials/   │ │ evals/ runner │ └──────────────┘ │ events + workflows │ │
│  │ processing   │ └───────────────┘                  │ jobs (thread pool) │ │
│  └──────────────┘                                    └────────────────────┘ │
│                    ┌─────────────────────────────────────────────────┐       │
│                    │ ai/ · AIClient → [Groq → Gemini] (OpenAI-compat)│       │
│                    │ fallback · structured output validation ·       │       │
│                    │ usage/cost/latency/attempt log · prompt registry│       │
│                    └─────────────────────────────────────────────────┘       │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────────────────┐
│ MongoDB                                                                      │
│  users · spaces · projects · materials · chunks(embedding[]) · concepts      │
│  mastery · mastery_history · conversations · messages · quiz_sessions        │
│  quiz_questions · learner_notes · recommendations · activity_events          │
│  ai_requests · jobs · eval_runs · eval_results        + local file storage   │
└──────────────────────────────────────────────────────────────────────────────┘
External: Groq API, Gemini API (both via OpenAI-compatible chat completions);
          fastembed (local ONNX embedding model, no network after first download)
```

Style: a **modular monolith**. One deployable API process (plus a static frontend). Services are separated by domain and communicate through function calls and events; background work runs on a thread pool inside the process. This is the smallest architecture that still has clean seams (jobs, events, provider) to grow into separate workers later.

## 2. Data model

Ownership chain: `User → Space → Project → *`. Every project-scoped document carries `project_id` and `user_id`, so isolation is one filter clause and background jobs keep ownership context in the job document.

| Collection | Purpose |
|---|---|
| `materials` | uploaded PDFs, status (`queued/processing/ready/failed`), stage, page/chunk counts, summary, job id |
| `chunks` | page-aware text passages with `embedding: float[384]` and kind (`text/table/ocr`) |
| `concepts` | extracted learnable concepts with importance and source pages |
| `mastery`, `mastery_history` | current estimate per concept and every update (for growth trends) |
| `conversations`, `messages` | tutor history with citations, tool calls, grounded flag, `ai_request_id` |
| `quiz_sessions`, `quiz_questions` | adaptive quiz state; questions store answer key, rubric, source pages, evaluation |
| `learner_notes` | persistent learner context (goal, preference, strength, weakness, tutor_note, pattern) |
| `recommendations` | next-step suggestions with trigger and status |
| `activity_events` | append-only event log (dedupe key) powering activity feeds, analytics, admin, workflows |
| `ai_requests` | one row per model call: feature, prompt name+version, provider, model, tokens, cost, latency, status, per-provider attempts, retrieval trace, tool calls, request id |
| `jobs` | background work: kind, status, stage, attempts, error, duration, dedupe key |
| `eval_runs`, `eval_results` | evaluation history with prompt versions and regressions |

## 3. Key flows

### Material processing (background)
`POST /materials` validates the PDF header and size, hashes the file (duplicate detection), stores it, emits `MATERIAL_UPLOADED`. The workflow handler enqueues `process_material` (dedupe key `process:<id>`). The job walks the stages the UI shows: **reading** (PyMuPDF text + `find_tables` rendered as markdown; pages with <40 chars go to the vision model for OCR, max 12) → **structure** (paragraph-aware chunking, 900 chars, 150 overlap, page ranges preserved) → **extracting** (concept extraction + summary via structured output; failures degrade gracefully) → **indexing** (local embeddings; chunks replaced idempotently). Then `MATERIAL_PROCESSED` → first recommendation. Bad files fail fast with a user-readable message (`ExtractionError.no_retry`); transient errors retry up to 3 times with backoff.

### Tutor turn (streaming)
1. Retrieval: embed the question (short follow-ups are expanded with the previous question) and rank the project's chunks by cosine similarity. `has_evidence` = best score ≥ 0.62 (calibrated: related questions score ≥0.78, unrelated ≤0.53 with bge-small).
2. Context composition: learner context (goal, weak/strong concepts, active notes by kind, recent mistakes — bounded, not the whole history), rolling conversation summary, last 6 turns.
3. Controlled tool phase: a fast-tier call with four tools (`search_materials`, `get_learning_state`, `get_recent_mistakes`, `start_quiz`). Tool arguments are validated with Pydantic; scope (user, project) is injected server-side, never taken from the model; results are appended as `<tool_results>` data. Max 2 calls, best-effort.
4. Answer: streamed over SSE with the versioned `tutor` prompt. The model must cite `[S#]` labels and end with `GROUNDED: yes|no`; the backend parses citations back to document/page and stores the grounded flag. When there is no evidence the prompt receives "(no passages…)" and the required refusal phrasing.
5. `TUTOR_INTERACTION_COMPLETED` → `post_tutor` job distils durable notes (preferences, confusions) into `learner_notes`.

### Adaptive quiz
Concept priority = `(1 − mastery)·(0.5 + importance) + 0.25·[last wrong] + 0.2·(1 − confidence) − penalties for concepts asked in the last two questions / repeated in the session`, sampled from the top three. Difficulty comes from the mastery band (easy <0.4, medium <0.7, else hard), stepping up after a correct answer at the same level and holding after a wrong one. At least one open-ended question per quiz. Questions are generated from the concept's source pages plus a semantic search, validated (4 distinct options, valid index, rubric present) before persisting. MCQ grading is deterministic; open answers are graded by a structured rubric evaluation (score, covered/missing points, accuracy issues, feedback). Each answer updates mastery idempotently (`source_ref = question id`). `QUIZ_COMPLETED` → `post_quiz` job: weakness/strength notes, repeated-mistake pattern detection, new recommendation.

### Mastery model
Exponential estimate in [0,1]: `α = max(0.12, 0.35 / (1 + 2·confidence))`; step `α · w · (result − score)` where `w` is the difficulty weight (0.6/1.0/1.4) for gains and `2 − w` for losses, so hard-correct moves more than easy-correct and easy-wrong moves more than hard-wrong. Confidence grows 0.15 per observation. Growth compares the current score to the last score older than 7 days (or the first recorded) and labels improving / stable / needs attention / new.

### Recommendations
A rule layer picks the action from evidence (no materials → upload; not assessed → diagnostic quiz; declining → review pages; weak → tutor; untested → quiz; all strong → harder quiz). The model then phrases a personalised title/reason via structured output; if the model is unavailable the rule wording is used. Previous active recommendations are superseded.

## 4. AI layer

- **Provider abstraction** (`services/ai/provider.py`): one `OpenAICompatProvider` serves Groq and Gemini; `AIClient` tries providers in order and falls back on 429/5xx/timeouts/invalid structured output. Tiers (`primary`, `fast`, `vision`) map to per-provider models so callers never name models.
- **Structured outputs**: JSON mode + schema in the prompt + Pydantic validation; invalid output triggers fallback to the next provider, and application code validates again (e.g. quiz option count) before persisting.
- **Prompt registry** (`services/prompts/registry.py`): every prompt has a name, version, responsibility and structured inputs; the version is stored on each `ai_requests` row and on eval runs, so behaviour changes are traceable.
- **Safety boundary**: every prompt states that `<material>`, `<learner_context>`, `<history>`, `<answer>` and tool results are data, not instructions; evals include injection cases; tool arguments are validated and scoped server-side; the model cannot address other users' or projects' data.
- **Observability**: every call records tokens, estimated cost (per-model price table), latency, status (`ok/fallback/error`), attempts per provider, retrieval hits, tool calls and request id. Logs are JSON with the same request id. The admin AI page answers "why was it slow / what failed / what did it cost / which prompt version".

## 5. Decisions and trade-offs

| Decision | Why | Trade-off / what I would change with more time |
|---|---|---|
| MongoDB instead of Postgres | flexible documents for context/events/traces; single store; user preference | no transactions across collections; uniqueness via indexes (sparse-null gotcha handled in `insert`) |
| In-process cosine instead of a vector index | simplest correct thing at MVP scale; no Atlas requirement | O(chunks) per query; move to Atlas Vector Search or pgvector past ~50k chunks |
| Local bge-small embeddings | free, no key, fast, good retrieval quality for study material | English-centric; a larger model would help long technical PDFs |
| Groq primary, Gemini fallback | fast + cheap; failover keeps the product up during rate limits | two vendors' JSON-mode quirks; structured outputs are validated defensively |
| Thread-pool jobs, no queue | user asked for no background infrastructure; keeps deployment to one process | work is lost if the process dies mid-job (mitigated: stale materials re-queued on startup); `enqueue()` is the single seam to swap in RQ/Celery |
| Router call for tools instead of tools on the streaming call | streaming + tool calling differs per provider; a fast-tier router keeps the answer path streamable and uniform | one extra cheap call per turn |
| Rule + model recommendations | always produce a next step even when AI is down; evidence-based | rules are hand-tuned |
| Evidence threshold gate + prompt refusal | two independent layers against confident hallucination | threshold is model-specific (calibrated for bge-small) |
| `create_index` at startup instead of migrations | prototype speed | production would use versioned migrations |

## 6. Security

JWT auth; admin role from configured emails; every project route re-checks ownership; retrieval, quiz, tutor and analytics all filter by `project_id` of an owned project; upload validates magic bytes, size and extension, stores files under `user/project` paths with sanitised names, and detects duplicates by content hash; request bodies are validated with Pydantic; AI tool calls are validated and scoped; prompts treat content as data; secrets live in env only.

## 7. Performance notes

Tutor answers stream; retrieval is a single numpy matmul per project; dashboards are computed from indexed collections (a few small aggregations per page — fine at MVP scale, would be cached/materialised at scale); the next quiz question is pre-generated when an answer is submitted so the learner never waits; materials process off the request path; cheap tiers (8B / Flash-Lite) are used for routing, OCR, summaries, context distillation and judging.
