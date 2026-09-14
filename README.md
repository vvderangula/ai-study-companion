# AI Study Companion

An AI-native learning workspace. Organise learning into **Spaces** and **Projects**, upload PDFs, learn with a **grounded AI Tutor** that cites pages and refuses what your materials don't cover, take **adaptive quizzes** with AI-graded open answers, and watch **concept mastery**, **growth** and **recommendations** evolve. An **Admin dashboard** exposes users, activity, AI usage/cost, evaluation results and system health.

Built for the "Full Stack AI Engineer" prototype challenge (see `docs/` for architecture, AI usage, evaluation and limitations).

---

## What it does (the learning loop)

```
Space → Project → Upload PDF → background processing (read · structure · extract concepts · index)
      → Tutor (retrieval + citations + refusal when unsupported, streaming, controlled tools)
      → Adaptive quiz (concept priority from mastery/mistakes, MCQ + AI-graded open answers)
      → Mastery model → Growth trends → Recommendation ("what should I do next?")
      → Persistent learner context feeds the next tutor turn and quiz
```

Feature checklist against the PRD "must have" list: authentication ✔ spaces ✔ projects ✔ PDF materials (text, tables, scanned pages via vision OCR) ✔ background processing with job states/retries/dedupe ✔ grounded tutor with citations ✔ unsupported-question handling ✔ adaptive quiz ✔ open-ended AI assessment ✔ concept mastery ✔ growth analysis ✔ recommendations ✔ project analytics ✔ global analytics ✔ activity tracking ✔ home dashboard ✔ admin dashboard (overview, users, user detail, spaces/projects, activity, learning analytics, AI usage, evaluation, health) ✔ AI usage & cost tracking ✔ evaluation with regression comparison ✔ prompt registry with versions ✔ streaming ✔ persistent learner context ✔ event-driven workflows ✔.

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Backend | Python 3.11, FastAPI | fast to build, typed, great PDF/AI tooling |
| Database | MongoDB (pymongo) | flexible documents for learner context, events, AI traces; one store for everything |
| Vector search | embeddings on chunk documents + in-process cosine (numpy) | a project holds ≤ a few thousand chunks; no vector DB needed for the MVP |
| Embeddings | fastembed `BAAI/bge-small-en-v1.5` (local ONNX, no key) | free, fast, calibrated threshold for "is there evidence?" |
| LLMs | **Groq** (Llama 3.3 70B / Llama 3.1 8B / Llama 4 Scout vision) primary, **Gemini** (2.5 Flash / Flash-Lite) fallback | both OpenAI-compatible → one provider implementation with automatic failover |
| Background work | in-process thread pool + `jobs` collection (states, stages, retries, dedupe) | no Redis/queue for the MVP; swap `enqueue()` for a real queue later |
| Frontend | React 18, Vite, TypeScript, Tailwind, recharts, react-markdown | |
| Auth | JWT (python-jose) + bcrypt; admin role from `ADMIN_EMAILS` | |
| Tests | pytest + mongomock + fake AI provider; vitest | whole learning loop runs offline |

## Quick start (local)

Prerequisites: Python 3.11, Node 18+, Docker (for MongoDB) — or a MongoDB Atlas URI.

```bash
# 1. MongoDB
docker compose up -d                      # mongo:7 on localhost:27017

# 2. Backend
cd backend
python -m venv .venv && .venv/Scripts/activate   # (Linux/mac: source .venv/bin/activate)
pip install -r requirements.txt
cp .env.example .env                      # then set GROQ_API_KEY / GEMINI_API_KEY, JWT_SECRET, ADMIN_EMAILS
python -m scripts.seed_demo               # creates demo@example.com / demo12345 and admin@example.com / admin12345
uvicorn app.main:app --reload             # http://127.0.0.1:8000  (OpenAPI docs at /docs)

# 3. Frontend
cd ../frontend
npm install
cp .env.example .env                      # VITE_API_BASE_URL=http://127.0.0.1:8000
npm run dev                               # http://localhost:5173
```

The first material upload downloads the embedding model (~30 MB) once.

### Running without AI keys

Set `AI_PROVIDER_ORDER=fake` to run the whole app offline with a deterministic provider (used by the test suite). Material processing, retrieval, mastery, analytics and admin views all work; tutor/quiz content is placeholder text.

## Configuration

All settings are environment variables (see `backend/.env.example`). The important ones:

| Variable | Purpose |
|---|---|
| `MONGO_URL`, `MONGO_DB` | database |
| `JWT_SECRET`, `ADMIN_EMAILS` | auth; emails listed get the admin role at registration |
| `AI_PROVIDER_ORDER` | `groq,gemini` (tried in order), or `fake` |
| `GROQ_API_KEY`, `GROQ_MODEL_*` | Groq models for primary / fast / vision tiers |
| `GEMINI_API_KEY`, `GEMINI_MODEL_*` | Gemini fallback models |
| `EMBEDDING_BACKEND` | `fastembed` (default) or `hash` (tests) |
| `EVIDENCE_MIN_SIMILARITY` | cosine threshold below which the tutor refuses (calibrated 0.62 for bge-small) |
| `JOB_BACKEND` | `thread` (default) or `inline` |
| `UPLOAD_DIR`, `MAX_UPLOAD_SIZE_MB` | file storage |

Secrets are never committed; `.env` is git-ignored.

## Tests

```bash
cd backend && python -m pytest -q        # 32 tests: auth, isolation, full learning loop, adaptive logic, jobs, provider wire format, evals
cd frontend && npm test                   # vitest
```

Backend tests use an in-memory MongoDB (mongomock), hash embeddings and a scripted fake AI provider, so they run in ~10 s with no network.

## Deployment

`render.yaml` describes a Render deployment (Docker API service with a persistent disk for uploads + static frontend). Any Docker host works:

```bash
docker build -t study-api ./backend
docker run -p 8000:8000 --env-file backend/.env study-api
docker build --build-arg VITE_API_BASE_URL=https://api.example.com -t study-web ./frontend
```

Use MongoDB Atlas for the database. Set `CORS_ORIGINS` to the frontend origin. Run `python -m scripts.seed_demo` once against the production database to create demo credentials.

## Repository layout

```
backend/
  app/
    api/routes/        auth, workspace (spaces/projects), materials, tutor, quiz, learning, analytics, admin, health
    core/              config, mongo helpers, auth, logging (JSON + request id), errors
    models/            document shapes (Pydantic) for every collection
    services/
      ai/              provider abstraction (Groq/Gemini/fake, fallback, usage+cost recording), embeddings
      prompts/         versioned prompt registry
      materials/       PDF pipeline: read → tables → OCR → chunk → concepts → summary → index
      retrieval.py     project-scoped semantic search
      learning/        workspace CRUD, mastery model + growth, learner context, recommendations
      tutor/           grounded tutor (streaming) + controlled tool layer
      quiz/            adaptive selection, question generation, grading
      analytics/       learner dashboards & analytics
      admin/           admin aggregations & health
      evals/           evaluation runner (+ app/evals/cases.json)
      events.py        activity events + handler dispatch
      jobs.py          background jobs (thread pool, retries, dedupe)
      workflows.py     event → job wiring (intelligent workflows)
  tests/
  scripts/seed_demo.py
frontend/src/
  pages/               Home, Spaces, Space, Project, Analytics, admin/*
  features/project/    Overview, Materials, Tutor, Quiz, Growth, Analytics tabs
  api/                 typed client + SSE streaming
docs/                  ARCHITECTURE, AI_USAGE, PROMPTS, EVALUATION, LIMITATIONS
```

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — diagram, data model, flows, decisions and trade-offs
- [docs/AI_USAGE.md](docs/AI_USAGE.md) — AI used to build the product vs AI inside the product, prompt registry
- [docs/PROMPTS.md](docs/PROMPTS.md) — the actual development prompts, unfiltered
- [docs/EVALUATION.md](docs/EVALUATION.md) — evaluation approach and regression tracking
- [docs/LIMITATIONS.md](docs/LIMITATIONS.md) — known limitations and what comes next
