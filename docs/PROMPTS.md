# Development prompts (unfiltered)

The product was built in a single Claude Code session (Claude Fable 5.1) inside VS Code. Below are the developer's prompts **verbatim**, in order, with the agent's main actions after each. Product-side prompts (the ones the deployed app sends to Groq/Gemini) live in `backend/app/services/prompts/registry.py`.

## 1. Analysis / architecture prompts

**Prompt 1** (with `Project_Requirements.pdf` attached):
> hey analyse this project and tell me what this is first ..later we can plan and build how to do this completely...

*Agent: read the 71-page PRD, summarised the product, engineering expectations, deliverables and scope risk.*

**Prompt 2:**
> https://github.com/vvderangula/studymate-ai.git analsye this repo...and does that repo will be usefull for you by any chance

*Agent: attempted to clone into a scratch directory; the developer interrupted.*

**Prompt 3:**
> clone into desktop

*Agent: cloned the repo to the Desktop, read its architecture, services, models, tests; assessed ~15–20% PRD coverage and recommended reusing the layered structure and PDF utilities but not the data model or AI layer.*

## 2. Stack / constraint prompts

**Prompt 4:**
> Dont go to access any api keys from the resumeup.ai or any productbridge anything...just be in this repository ,and work on this which techstack and api keys will be needed for you

*Agent: saved a standing rule to never read other projects' keys; proposed a stack (initially FastAPI + Postgres/pgvector + Redis/RQ + Anthropic + Voyage embeddings) and the required keys.*

**Prompt 5:**
> its for mvp only... and for embeddings right

*Agent: confirmed Voyage was embeddings-only and recommended local embeddings with no key.*

**Prompt 6:**
> ok start building

*Agent: checked the toolchain, started Docker services, installed dependencies, wrote config/db/models/AI provider/prompt registry/auth/events/jobs/processing/retrieval/mastery for the first stack.*

**Prompt 7:**
> hey what techstacks you are usign

*Agent: listed the stack in use.*

**Prompt 8:**
> architecture

*Agent: described the layered architecture and the key mechanisms (isolation, grounded tutor, tool boundary, adaptive quiz, mastery, events, observability, evaluation).*

**Prompt 9** (the decisive re-direction):
> use mongodb, as well as go with groq api's and gemini apis as fallbacks...thats it i think no need of background jobs, for this mvp

*Agent: flagged the PRD's background-processing requirement in one sentence, then rewrote the data layer for MongoDB, replaced the AI provider with an OpenAI-compatible implementation (Groq primary, Gemini fallback), replaced the queue with an in-process thread pool + jobs collection, and continued building the tutor, quiz, analytics, admin, evaluation runner, API routes, tests, frontend and documentation.*

## 3. Backend / database / AI-feature prompts

No further developer prompts were needed for these areas; the agent derived them from the PRD sections (tutor §16–23, quiz §24–28, mastery §29–32, workflows §33–38, context §39–40, observability §43–45, evaluation §46–47, admin §56–64) and the constraints above.

## 4. Debugging / testing prompts

All debugging in this session was agent-driven: the agent ran `pytest`, read failures (header dict leak in a test helper, PyMuPDF-generated PDFs hashing differently, naive vs aware datetimes from Mongo, an unregistered router prompt, system events overwriting "last activity", a Windows file-handle ordering bug in upload validation, and a sparse-unique-index null collision found by the live smoke test) and fixed them without additional developer prompts.

## 5. Documentation prompts

The documentation set (README, ARCHITECTURE, AI_USAGE, PROMPTS, EVALUATION, LIMITATIONS) was produced by the agent as part of the build, per the PRD's submission requirements, without a separate prompt.

---

*This file should be appended to as development continues (deployment, demo video, follow-up iterations).*
