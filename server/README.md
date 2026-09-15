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
```

The retrieval layer creates the `repositories`, `code_chunks`, `embeddings`, and
`review_context` tables in Neon on the first review. Each review fetches full text
for changed files, chunks bounded relative-import dependencies when available, and
retrieves across the repository's stored chunks. Retrieval is incremental: the MVP
does not clone or index the entire repository up front. A repository's searchable
context grows as PRs are reviewed, so unvisited files are not available until they
are fetched through a reviewed PR or another indexing workflow. The Neon project
must have the `vector` extension enabled. Historical chunks from previous PR head
SHAs remain searchable for now; this preserves useful context but can leave stale
duplicate versions that rank highly. A later cleanup or version-selection policy is
needed before treating the index as a long-lived repository source of truth.

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
