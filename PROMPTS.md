# Claude Code Prompts

This file contains the tailored prompts that could be used in Claude Code to build the AI Study Companion from the product requirements. They are organised in the order that keeps the work testable and deployable.

## 1. Product analysis and architecture

```text
Read the product requirements carefully and first explain the product in plain language. Identify the main user journeys, required screens, backend capabilities, data that must persist, AI features, security boundaries, and the smallest credible MVP. Do not write code yet. Call out ambiguities and high-risk areas such as PDF processing, grounded answers, adaptive quizzes, background work, and multi-user data isolation.
```

```text
Design a modular-monolith architecture for this learning workspace. Use a React + Vite + TypeScript frontend and a FastAPI + Python 3.11 backend. Use MongoDB for all persistent application data. Keep the architecture simple enough for an MVP but leave clear boundaries for services, jobs, events, AI providers, retrieval, and evaluation. Describe the module tree, API boundaries, collection ownership, authentication flow, and deployment shape before implementing it.
```

## 2. Stack and constraints

```text
Implement this project only inside the current repository. Do not read credentials, files, or code from unrelated projects. Use MongoDB through pymongo, JWT authentication, FastAPI, React, Vite, TypeScript, Tailwind, and Vitest. Use local fastembed embeddings so embeddings do not require a paid API key. Keep all secrets in environment variables and provide safe .env.example files.
```

```text
Use Groq as the primary AI provider and Gemini as the fallback provider. Both providers should use one OpenAI-compatible client abstraction. Support configurable primary, fast, and vision model tiers. Add timeouts, provider fallback, structured-output validation, usage tracking, estimated cost tracking, and clear errors. The rest of the application must not depend directly on a specific provider or model name.
```

```text
The MVP does not need Redis or a separate queue service. Implement reliable-enough background processing with an in-process thread pool and a jobs collection that records status, stage, attempts, errors, duration, and deduplication. Keep enqueue() isolated so it can later be replaced by a real worker queue.
```

## 3. Backend foundation

```text
Build the FastAPI backend foundation. Add typed environment configuration, MongoDB connection helpers, collection constants, startup indexes, JSON logging, request IDs, health checks, application error handling, and CORS. Add JWT authentication with password hashing and an admin role based on configured email addresses. Keep tests able to inject mongomock and fake AI services.
```

```text
Implement the ownership model User -> Space -> Project. Every project-scoped query must verify both the authenticated user and the project ID. Add routes and services for creating, listing, updating, and deleting spaces and projects. Do not trust user or project IDs supplied by an AI tool or client when checking access.
```

## 4. Materials and retrieval

```text
Implement PDF material upload for authenticated projects. Validate the extension, PDF magic bytes, and maximum size. Store files under user/project paths with sanitized names and a content hash for duplicate detection. Persist material processing state and make failures user-readable. After upload, emit an event and enqueue a deduplicated processing job.
```

```text
Build the material-processing pipeline with visible stages: reading, structure, extracting, and indexing. Use PyMuPDF for text and tables, detect image-only pages, use the vision AI tier for bounded OCR, chunk text with page metadata, extract concepts and a summary using structured AI responses, and create local fastembed vectors. Make retries bounded and make each stage idempotent.
```

```text
Implement project-scoped semantic retrieval using the stored embeddings and in-process cosine similarity. Return source labels, page numbers, chunk text, and similarity scores. Add an evidence threshold so unrelated questions produce no evidence rather than fabricated context. Keep retrieval restricted to the authenticated project.
```

## 5. Tutor and learner context

```text
Build a grounded tutor service. For each question, retrieve relevant project passages, combine them with bounded learner context and recent conversation history, and call a controlled tool-routing phase before the answer when needed. Available tools are search_materials, get_learning_state, get_recent_mistakes, and start_quiz. Validate tool arguments with Pydantic and inject user/project scope on the server.
```

```text
Make the tutor answer stream over Server-Sent Events. Require page citations such as [S1], parse citations back to stored sources, record whether the answer was grounded, and refuse clearly when the materials do not support the question. Treat material text, learner context, history, answers, and tool results as untrusted data rather than instructions.
```

```text
Add persistent learner context. After tutor and quiz activity, use a structured fast-tier call to distil durable goals, preferences, strengths, weaknesses, confusion points, and learning patterns. Keep recent history bounded and avoid storing sensitive or irrelevant content.
```

## 6. Adaptive quiz and mastery

```text
Implement adaptive quizzes using project concepts, importance, mastery, confidence, recent mistakes, difficulty, and repetition penalties. Generate both MCQ and open-ended questions from retrieved source pages. Validate generated JSON before persistence: MCQs need distinct options and a valid answer index; open questions need a rubric and source pages.
```

```text
Implement deterministic MCQ grading and structured AI grading for open answers. Return score, covered points, missing points, accuracy issues, and actionable feedback. Make answer submission idempotent and update concept mastery exactly once per question.
```

```text
Implement the mastery model, history, growth labels, and recommendations. Use an interpretable score in the range 0 to 1, confidence, difficulty weighting, and source references. Recommendations should always have a rule-based fallback when AI is unavailable and should be superseded when a newer recommendation is created.
```

## 7. Analytics, admin, and observability

```text
Add append-only activity events and event handlers for uploads, tutor interactions, quiz completion, mastery changes, and recommendations. Record AI request feature, prompt name/version, provider attempts, model, token counts, estimated cost, latency, status, retrieval trace, and tool calls. Provide analytics for learners and administrators without exposing another user's project data.
```

```text
Build admin-only routes and screens for overview, users, user details, spaces/projects, activity, learning analytics, AI usage, evaluation runs, and system health. Enforce the admin role in the backend, not only in the frontend.
```

## 8. Frontend implementation

```text
Build the React frontend around the backend API. Add protected routing, login, registration, home dashboard, spaces, projects, materials, tutor, quiz, growth, analytics, and admin pages. Use a typed API client with JWT headers, consistent error handling, multipart PDF upload, and SSE tutor streaming. Keep the API base URL in VITE_API_BASE_URL and never expose backend secrets.
```

```text
Make the project workspace workflow clear: users should be able to create a project, upload a PDF, see processing stages, open the tutor, start an adaptive quiz, review mastery and growth, and follow recommendations. Handle loading, empty, processing, failed, unauthorized, and retry states explicitly.
```

## 9. Testing and evaluation

```text
Write focused backend tests for authentication, user isolation, MongoDB helpers, provider fallback, structured output validation, PDF processing, jobs, retrieval evidence thresholds, tutor refusal, quiz grading, idempotent mastery updates, recommendations, and admin access. Use mongomock, fake providers, and hash embeddings so tests do not require network access or API keys.
```

```text
Add frontend tests for protected routes, login and registration states, API errors, project navigation, material processing states, quiz interactions, and tutor streaming. Run the backend and frontend tests, fix failures at their root cause, and do not weaken assertions just to make tests pass.
```

```text
Create an evaluation runner with representative grounded questions, unsupported questions, citation cases, prompt-injection cases, quiz cases, and provider-failure cases. Store evaluation runs and results with prompt versions, and report regressions against the previous run.
```

## 10. Deployment and handoff

```text
Prepare this repository for deployment. Keep the FastAPI backend in Docker and deploy it as a Render web service with /health as the health check. Deploy the Vite frontend as a static Vercel or Netlify site. Document MongoDB Atlas setup, required environment variables, CORS_ORIGINS, VITE_API_BASE_URL, secret handling, upload-storage limitations, seed-demo usage, and post-deployment smoke tests. Do not commit credentials.
```

```text
Before final handoff, inspect the git diff, run available tests and build commands, check for secrets and broken links, verify the production configuration, and provide a concise summary of changed files, known limitations, and exact local and deployment commands.
```