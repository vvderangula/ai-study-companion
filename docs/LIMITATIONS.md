# Known limitations & future improvements

## Known limitations

**Documents**
- PDF only. Tables are extracted with PyMuPDF's table finder (works for ruled tables, weaker on whitespace-aligned ones). Diagrams are not interpreted unless the page is image-only, in which case the whole page goes through vision OCR (max 12 pages per document).
- Scanned pages depend on the vision model's transcription quality.

**AI**
- Groq free-tier rate limits are real; the Gemini fallback mitigates but does not eliminate slowdowns. Costs are *estimated* from a static price table.
- Structured output relies on JSON mode plus validation rather than strict schema enforcement; invalid outputs fall back to the next provider and, if all fail, surface as a clear error (never silently corrupting learning state).
- Tool calling is done in a separate routing call rather than inside the streamed answer, adding ~200–400 ms per turn.
- Open-answer grading is a single model judgement; no calibration against human graders.

**Retrieval**
- In-process cosine similarity over a project's chunks: fine to tens of thousands of chunks, not beyond. No hybrid (keyword) retrieval, no re-ranking, no cross-material deduplication.
- The evidence threshold is calibrated for `bge-small-en-v1.5`; changing the embedding model requires re-calibration.

**Learning model**
- Mastery is a heuristic estimate (difficulty-weighted exponential update), not a psychometric model; confidence is a simple evidence counter.
- Concepts are extracted per material; merging across materials is by slug only.

**Background processing**
- In-process thread pool: jobs do not survive a process restart (stale materials are re-queued on startup, but partial work is lost) and cannot scale horizontally. This is an explicit MVP choice; `jobs.enqueue()` is the single seam to replace.

**Evaluation**
- Small case set; LLM judge; grounded cases are templated rather than gold-labelled.

**Scale / infra**
- Single API process; no caching layer; dashboards recompute aggregates per request; files stored on local disk (persistent disk on Render, not object storage); no rate limiting on the API itself.

**Security**
- JWT without refresh/revocation; no email verification; admin role is assigned from a configured email list; uploaded files are validated by header, size and extension only (no antivirus scan).

**UI**
- Prototype styling; no offline support; charts are basic; limited accessibility review.

## Future improvements (what I would build next)

1. **Real queue** (Redis + RQ or a managed queue) behind the existing `enqueue()` seam; separate worker deployment; per-stage progress via server-sent events instead of polling.
2. **Retrieval quality**: hybrid BM25 + vector, re-ranking, chunk-level page thumbnails so citations can open the exact page.
3. **Mastery**: Bayesian knowledge tracing or an IRT-style difficulty model; spaced-repetition scheduling from the mastery history; concept prerequisites graph.
4. **Evaluation**: gold-labelled per-project datasets, pairwise prompt A/B runs, scheduled regression runs in CI, human-review queue.
5. **Learning experiences**: flashcards generated from concepts, revision plans, concept maps from extracted relationships, voice tutor.
6. **Ops**: OpenTelemetry traces across request → job → model call, cost budgets per user, response caching for repeated questions, object storage for uploads.
7. **Product**: multi-document projects with material-level filters in the tutor, collaborative spaces, notifications when material is ready or a recommendation changes.
