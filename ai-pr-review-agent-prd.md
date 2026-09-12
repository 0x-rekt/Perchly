# PRD: AI Pull Request Review Agent

**Status:** Draft v1
**Owner:** Kolay
**Doc type:** Product Requirements Document (with embedded technical design)

---

## 1. Summary

An open-source, production-grade service that automatically reviews GitHub pull requests using four parallel LLM-based specialist agents (security, code quality, test coverage, documentation). Findings are aggregated into a single structured review posted back to the PR. Low-confidence findings are routed to a human approval queue instead of being posted directly. The system is fully observable (every agent step, LLM call, and decision is logged), tracks cost/latency in real time, and improves over time by learning from which findings were accepted vs. rejected.

This is a portfolio project intended to demonstrate production AI-engineering skill: multi-agent orchestration, retrieval-augmented reasoning over code, human-in-the-loop safety, evals as a CI gate, and real observability — not just a prompt wrapped in a webhook handler.

---

## 2. Problem Statement

Human PR review is a bottleneck: reviewers are inconsistent, slow under load, and tend to skip low-glamour categories (docs, test coverage) in favor of skimming the diff. Existing "AI review" bots are typically single-shot, single-model, low-precision, and produce noisy comments that erode trust — teams turn them off within weeks.

**The core product bet:** a review agent earns trust by being *right more than it's wrong*, and by knowing when it doesn't know. That means: specialist decomposition (a security-focused prompt catches different things than a generalist one), grounding in actual codebase context (not just the diff in isolation), and an explicit confidence-based escalation path instead of always speaking with false certainty.

---

## 3. Goals

- Automatically review every opened/updated PR within a defined SLA (target: first comment within 3 minutes of webhook receipt).
- Cover four review domains — security, code quality, test coverage, documentation — as independently reasoning specialist agents.
- Ground every finding in retrieved codebase context (not diff-only reasoning).
- Route low-confidence findings to a human approval queue rather than posting them directly.
- Provide full traceability: every agent action, tool call, and LLM call is recorded and queryable.
- Provide a live dashboard of review volume, cost per review, and latency per phase.
- Improve finding quality over time using outcome data (merged/dismissed/edited findings).
- Ship in gated phases, each with its own test suite, eval suite, and a written checkpoint before the next phase starts.

### Non-goals (v1)

- Auto-approving or auto-merging PRs.
- Fixing code automatically (suggesting a diff is in scope; applying it is not, for v1).
- Supporting non-GitHub platforms (GitLab, Bitbucket) — architecture should not preclude it later, but it's not built now.
- Fine-tuning a custom model. Learning from outcomes happens via retrieval/few-shot, not weight updates.
- Supporting monorepos above a certain size (>50k files) without a separate indexing strategy — flagged as a known limitation, not solved in v1.

---

## 4. Users & Use Cases

**Primary user:** a software engineer or maintainer on a repo with the GitHub App installed.

**Secondary user:** a designated reviewer/approver who triages the HITL queue.

### Core use cases
1. Engineer opens a PR → agent posts a structured review within minutes, covering all four domains.
2. Engineer pushes a new commit to an existing PR → agent re-reviews only the delta, avoids repeating unchanged findings.
3. Agent is uncertain about a finding (e.g., a possible but unconfirmed SQL injection) → it's queued for human approval instead of posted.
4. Approver reviews the HITL queue, accepts/edits/rejects each finding → accepted ones get posted, rejected ones are logged as negative examples.
5. Maintainer opens the dashboard → sees review volume, average cost per PR, p50/p95 latency per agent, and approval-queue backlog.
6. Maintainer wants to know why an agent flagged something → drills into the trace for that specific LLM call, including the retrieved context it reasoned over.

---

## 5. Functional Requirements

### 5.1 Webhook ingestion
- Receive GitHub `pull_request` webhook events (`opened`, `synchronize`, `reopened`).
- Verify webhook signature (HMAC with shared secret from the GitHub App).
- Enqueue a review job; respond to GitHub within GitHub's timeout window (<10s) regardless of how long the actual review takes.
- Deduplicate rapid-fire `synchronize` events (debounce ~30s) to avoid re-reviewing on every force-push.

### 5.2 Context retrieval
- Fetch the PR diff via the GitHub API.
- Chunk the touched files (and their direct dependents/dependencies where feasible) using AST-aware chunking.
- Embed and store/query chunks in a vector index scoped to that repo.
- Retrieve top-k relevant chunks per specialist agent's query (each agent queries independently, since a security agent's relevant context differs from a docs agent's).

### 5.3 Specialist agents (parallel)
Each agent:
- Receives: the diff, retrieved context, PR metadata (title, description, linked issues).
- Reasons using tool calls as needed (e.g., "fetch full file", "search for usages of this function").
- Emits zero or more structured findings: `{file, line_range, severity, confidence, category, message, suggested_fix?}`.
- Runs independently and in parallel from the other three; a failure/timeout in one agent must not block the others.

Domains:
- **Security** — injection, auth/authz gaps, secret leakage, unsafe deserialization, dependency risk.
- **Code quality** — complexity, duplication, naming, dead code, anti-patterns.
- **Test coverage** — untested branches/functions introduced by the diff, missing edge cases.
- **Docs** — missing/outdated docstrings, README/changelog drift, undocumented public API changes.

### 5.4 Aggregation
- Merge all findings from all four agents into one structured review object.
- Deduplicate overlapping findings (e.g., quality and security both flag the same line).
- Apply a confidence threshold: findings above threshold → posted directly; below threshold → HITL queue.
- Threshold is configurable per repo and per category (a team may want a stricter bar for "security" than for "docs").

### 5.5 GitHub posting
- Post one review with inline comments at the correct diff positions, using the GitHub Checks/Reviews API.
- Summary comment at the top of the review listing counts per category and a one-line verdict (e.g., "3 findings, 1 pending human review").
- Update the check run status (`success` / `neutral` / `action_required`) based on severity of unresolved findings.

### 5.6 Human-in-the-loop queue
- Persist low-confidence findings with full context (diff snippet, retrieved evidence, agent's reasoning summary).
- Simple UI: approve (posts as-is), edit (modify message/severity then post), reject (discard, log as negative example).
- Queue has an age-based escalation (e.g., Slack/email ping if unresolved after N hours) — configurable, not required for MVP.

### 5.7 Observability
- Every LLM call, tool call, and agent decision is recorded as a span with: input, output, token counts, cost, latency, model used.
- Traces are queryable by PR, by agent, by time range.
- Dashboard surfaces: reviews/day, cost/review, p50/p95 latency by phase (retrieval, agent reasoning, aggregation, posting), HITL queue depth and age, acceptance rate per category.

### 5.8 Learning loop
- Every finding's final outcome is recorded: posted-as-is, posted-after-edit, rejected-in-queue, later resolved/dismissed on GitHub (via follow-up webhook on review comment resolution, if tracked).
- Accepted/rejected findings become a retrieval pool: each specialist agent retrieves a small number of similar past findings (with their outcomes) as few-shot context before reasoning, to calibrate its own confidence and phrasing.

---

## 6. System Architecture

```
GitHub PR event
      │
      ▼
Webhook receiver (FastAPI) ──► verifies signature, enqueues job
      │
      ▼
Temporal workflow (durable, per-PR)
      │
      ├─► Context retrieval activity (diff fetch, chunk, embed, vector query)
      │
      ├─► Fan-out: 4 parallel activities, one per specialist agent
      │     each: LLM reasoning loop (tool use) → structured findings
      │
      ├─► Fan-in: Aggregator activity (dedupe, confidence routing)
      │
      ├─► Branch:
      │     ├─ high-confidence findings → Post-to-GitHub activity
      │     └─ low-confidence findings  → HITL queue (Temporal signal wait)
      │
      └─► On human decision signal → Post-to-GitHub activity (approved subset)

Every activity emits OpenTelemetry spans → Postgres/Timescale hypertable
Continuous aggregates → dashboard (cost, latency, volume)
Outcome data → Postgres → retrieval pool for future few-shot grounding
```

### Recommended stack

| Layer | Choice | Why |
|---|---|---|
| Orchestration | Temporal (Python SDK) | Durable execution, native support for the human-approval pause/resume via signals, retries/timeouts per agent |
| Agent reasoning | LangGraph or raw tool-calling loop, per specialist | Runs inside a Temporal activity; handles the ReAct-style "retrieve → reason → emit finding" loop |
| LLM | Anthropic API (Claude), structured tool-use output | Typed findings via Pydantic schema, not free text |
| Embeddings | Voyage AI `voyage-code-3` | Code-specific embedding model |
| Vector store | pgvector on the same Postgres instance | Avoids a second database; simpler ops story |
| Time-series metrics | TigerData/Timescale hypertables + continuous aggregates | Real-time cost/latency rollups without custom batch jobs |
| Tracing | OpenTelemetry, optionally paired with Langfuse | Per-call spans with cost/latency/token attributes |
| GitHub integration | GitHub App (not PAT), `githubkit`/PyGithub | Scoped permissions, webhook signature verification, Checks API |
| Webhook/API server | FastAPI | Lightweight, async-friendly, pairs well with Temporal's Python SDK |
| Evals | promptfoo or custom harness, golden PR dataset | CI gate before merging prompt/logic changes |
| Frontend | Next.js | HITL queue UI + dashboard, reading from continuous aggregates |
| Language | Python end-to-end | Ecosystem maturity for agents; matches Temporal/LangGraph/Anthropic SDKs |

---

## 7. Data Model (key entities)

- **PullRequest** — repo, PR number, head SHA, status, last-reviewed SHA.
- **ReviewRun** — PR id, started_at, completed_at, workflow_id (Temporal), status.
- **Finding** — review_run id, agent (category), file, line_range, severity, confidence, message, suggested_fix, status (posted / queued / rejected / edited).
- **HITLDecision** — finding id, decision, editor, edited_message?, decided_at.
- **AgentSpan** — review_run id, agent, span_type (llm_call/tool_call), input, output, tokens_in, tokens_out, cost, latency_ms, model, timestamp (hypertable).
- **OutcomeExample** — finding id, final_outcome, embedding (for retrieval as few-shot context).

---

## 8. Key Interfaces

### Webhook payload (subset consumed)
`action`, `pull_request.number`, `pull_request.head.sha`, `pull_request.base.sha`, `repository.full_name`.

### Internal finding schema (shared across all agents)
```json
{
  "category": "security | quality | test_coverage | docs",
  "file": "string",
  "line_start": "int",
  "line_end": "int",
  "severity": "info | warning | critical",
  "confidence": "float 0-1",
  "message": "string",
  "suggested_fix": "string | null"
}
```

### GitHub posting
- Reviews API for inline comments tied to diff positions.
- Checks API for overall status.

---

## 9. Non-Functional Requirements

- **Latency:** first review comment posted within 3 minutes of webhook receipt for a PR under ~500 changed lines.
- **Cost:** target average cost per review tracked and visualized; alert if p95 cost per review exceeds a configurable threshold (guards against runaway agent loops).
- **Reliability:** a single agent's failure/timeout must not fail the whole review — aggregator posts partial results and logs the gap.
- **Security:** webhook signature verification mandatory; GitHub App credentials and Anthropic/Voyage API keys stored in a secrets manager, never in code or logs; no PR content persisted beyond what's needed for the retrieval pool and audit trail.
- **Idempotency:** re-processing the same webhook delivery (GitHub's at-least-once delivery) must not double-post reviews.

---

## 10. Success Metrics

- **Precision proxy:** % of posted findings not dismissed/reverted by the PR author within 48h.
- **HITL efficiency:** median time-to-decision in the approval queue.
- **Coverage:** % of PRs reviewed within SLA.
- **Cost efficiency:** cost per review trending down (or flat) as the outcome-retrieval loop matures.
- **Trust signal:** repos that keep the GitHub App installed after 30 days (proxy for "didn't get turned off due to noise").

---

## 11. Phased Rollout (gated)

Each phase ends with: tests passing, an eval suite passing against a golden PR set, and a short written checkpoint (what shipped, what was learned, what's explicitly deferred) before the next phase starts.

1. **Phase 0 — Skeleton:** webhook receiver, single generalist agent (no specialization), direct posting, no HITL, no vector search. Prove the end-to-end loop works.
2. **Phase 1 — Specialists + retrieval:** split into 4 specialist agents, add codebase context retrieval via pgvector, keep everything else the same.
3. **Phase 2 — Orchestration hardening:** move from ad-hoc async calls to Temporal workflows; add retries, timeouts, partial-failure handling.
4. **Phase 3 — HITL:** confidence-based routing, approval queue UI, decision persistence.
5. **Phase 4 — Observability:** OpenTelemetry spans, Timescale hypertables, continuous aggregates, dashboard.
6. **Phase 5 — Learning loop:** outcome logging, few-shot retrieval pool feeding back into agent prompts.
7. **Phase 6 — Polish/OSS readiness:** documentation, setup script, example repo, contribution guide.

---

## 12. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Noisy/low-precision findings erode trust fast | Confidence-based HITL routing from day one of specialist agents; track precision proxy metric explicitly |
| Cost runaway from large PRs or agent loops | Per-review cost cap + alerting via continuous aggregates; cap retrieval/tool-call iterations per agent |
| Vector index goes stale as codebase evolves | Re-index on merge to default branch, not just on PR open |
| GitHub rate limits under load | Use GitHub App installation tokens (higher limits), batch API calls, backoff/retry |
| HITL queue backs up and defeats the purpose | Age-based escalation; make thresholds tunable per repo so teams can dial sensitivity |

---

## 13. Open Questions

- Should the docs/quality agents have a *lower* default confidence bar than security (i.e., more willing to post directly since stakes are lower)?
- How should re-reviews on `synchronize` handle previously-posted-but-now-irrelevant findings — auto-resolve, or leave for the human?
- Is a single shared vector index per repo sufficient, or does a monorepo need per-package indexing to keep retrieval relevant?
- What's the right unit for the "written checkpoint" — a short ADR per phase, or a changelog entry? (Leaning ADR for portfolio value.)
