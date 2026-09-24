# Perchly API

Run the development server:

```powershell
uv run uvicorn app.main:app --reload
```

GitHub should send webhooks to `POST /webhooks/github`.

For every accepted pull-request event, the server logs a start line followed by either
the fetched diff size or an error traceback. Keep the terminal running while testing.

Required local configuration in `.env`:

```env
GITHUB_APP_ID=your-app-id
GITHUB_WEBHOOK_SECRET=your-webhook-secret
GITHUB_PRIVATE_KEY_PATH=./your-github-app-private-key.pem
GEMINI_API_KEY=your-gemini-api-key
DATABASE_URL=postgresql://user:password@host/dbname?sslmode=require
# Optional retrieval settings
GEMINI_EMBEDDING_MODEL=gemini-embedding-2
EMBEDDING_DIMENSIONS=768
PERCHLY_AUTO_POST_THRESHOLD=0.90
PERCHLY_SECURITY_AUTO_POST_THRESHOLD=0.95
PERCHLY_MAX_AUTO_POST_FINDINGS=20
# Optional OpenTelemetry console exporter for local tracing diagnostics.
# Keep disabled in production unless logs are protected from source-code data.
PERCHLY_OTEL_CONSOLE_EXPORT=false
# Optional OTLP/HTTP collector endpoint, e.g. Grafana Tempo or Jaeger
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces
```

Perchly creates OpenTelemetry spans for Temporal activities, Gemini generation,
and Gemini embedding calls. The SDK spans carry review, repository, agent,
phase, model, token, and error attributes; the PostgreSQL `agent_spans` table
remains the queryable dashboard sink. Set `PERCHLY_OTEL_CONSOLE_EXPORT=true`
locally to print completed SDK spans while debugging instrumentation.

Findings are auto-posted only when all specialists succeed and every finding meets
the configured confidence policy. Critical security findings, any specialist
failure, and mixed-confidence reviews require approval. The approval queue is the
next Phase 3 step; until it is connected, `NEEDS_APPROVAL` reviews are held without
posting.

The retrieval layer creates the `repositories`, `code_chunks`, `embeddings`, and
`review_context` tables in cloud PostgreSQL on the first review. Each review fetches full text
for changed files, chunks bounded relative-import dependencies when available, and
retrieves across the repository's stored chunks. Retrieval is incremental: the MVP
does not clone or index the entire repository up front. A repository's searchable
context grows as PRs are reviewed, so unvisited files are not available until they
are fetched through a reviewed PR or another indexing workflow. The cloud PostgreSQL project
must have the `vector` extension enabled. Historical chunks from previous PR head
SHAs remain searchable for now; this preserves useful context but can leave stale
duplicate versions that rank highly. A later cleanup or version-selection policy is
needed before treating the index as a long-lived repository source of truth.

Reviews routed to `NEEDS_APPROVAL` are persisted in cloud PostgreSQL tables
`review_queue` and `review_decisions`. Queue payloads retain the aggregated findings,
specialist failures, PR metadata, diff, repository files, and retrieved contexts so
approval can reconstruct the review without rerunning Gemini.
Approval-required Temporal workflows wait durably for one of the `approve_review`,
`reject_review`, or `edit_review` signals. Approved and edited reviews are posted
after the signal; rejected reviews are recorded without posting.

### Agent-authored fix PRs

The approval console supports a two-step fix workflow:

```text
POST /reviews/queue/{queue_id}/findings/{finding_id}/fix-pr/preview
POST /reviews/fix-pr/{fix_id}/create
```

The first call generates and stores a unified diff without changing GitHub. The
console displays the affected files and diff; the second call requires explicit
reviewer confirmation. Perchly then creates or reuses a `perchly/fix/...` branch,
updates one or more files, and opens a pull request against the original PR's base
branch. The `fix_prs` table stores the patch, reviewer, status, branch, URL, and
timestamps.

The GitHub App must have `Contents: Read and write`, `Pull requests: Read and write`,
and `Metadata: Read-only`. Generated PR bodies contain a hidden Perchly marker. The
webhook receiver ignores marked generated PR events, so humans can review and merge
the PR without Perchly recursively reviewing its own change.

Run the Phase 0 automated checks:

```powershell
uv run pytest
```

Golden PR diffs for later model-quality evaluation live in `app/evals/fixtures/`.

Run the live Phase 0 golden-model gate (uses `GEMINI_API_KEY` and consumes API quota):

```powershell
uv run python -m app.evals.run
```

## Layout

```text
app/
  core/       Configuration
  routers/    HTTP endpoints
  schemas/    Validated request models
  services/   GitHub-specific domain logic
  workers/    Background job boundaries
  main.py     FastAPI application factory/module
```
