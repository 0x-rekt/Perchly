import asyncio
import json
import logging
import re
import ssl
import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable
from urllib.parse import unquote, urlparse

from pg8000.exceptions import DatabaseError as PGDatabaseError
from pg8000.exceptions import InterfaceError as PGInterfaceError
from pgvector import Vector

from app.core.config import EMBEDDING_DIMENSIONS, database_url
from app.schemas.findings import Finding, assign_finding_ids

_LOG = logging.getLogger(__name__)


class ReviewQueueService:
    """Persist human-review queue items and decisions in cloud PostgreSQL."""

    async def enqueue(
        self,
        *,
        delivery_id: str,
        repository: str,
        pr_number: int,
        head_sha: str,
        review_payload: dict[str, Any],
        specialist_failures: dict[str, str],
        reason: str,
        workspace_id: int | None = None,
    ) -> int:
        return await asyncio.to_thread(
            self._enqueue,
            delivery_id=delivery_id,
            repository=repository,
            pr_number=pr_number,
            head_sha=head_sha,
            review_payload=review_payload,
            specialist_failures=specialist_failures,
            reason=reason,
            workspace_id=workspace_id,
        )

    async def record_decision(
        self,
        *,
        queue_item_id: int,
        decision: str,
        reviewer: str,
        edited_review: dict[str, Any] | None = None,
        comment: str | None = None,
    ) -> int:
        return await asyncio.to_thread(
            self._record_decision,
            queue_item_id=queue_item_id,
            decision=decision,
            reviewer=reviewer,
            edited_review=edited_review,
            comment=comment,
        )

    async def record_automatic_decision(
        self,
        *,
        delivery_id: str,
        repository: str,
        pr_number: int,
        head_sha: str,
        review_payload: dict[str, Any],
        reason: str,
    ) -> int:
        return await asyncio.to_thread(
            self._record_automatic_decision,
            delivery_id=delivery_id,
            repository=repository,
            pr_number=pr_number,
            head_sha=head_sha,
            review_payload=review_payload,
            reason=reason,
        )

    async def record_reviewer_decision(
        self, *, queue_item_id: int, decision: dict[str, Any]
    ) -> int:
        return await self.record_decision(
            queue_item_id=queue_item_id,
            decision=decision["decision"],
            reviewer=decision["reviewer"],
            edited_review=decision.get("edited_review"),
            comment=decision.get("comment"),
        )

    async def record_external_outcome(
        self,
        *,
        repository: str,
        pr_number: int,
        head_sha: str,
        final_outcome: str,
    ) -> int:
        return await asyncio.to_thread(
            self._record_external_outcome,
            repository=repository,
            pr_number=pr_number,
            head_sha=head_sha,
            final_outcome=final_outcome,
        )

    async def list_items(self, *, status: str = "pending", workspace_id: int | None = None) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._list_items, status, workspace_id)

    async def get_item(self, queue_item_id: int, workspace_id: int | None = None) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_item, queue_item_id, workspace_id)

    async def save_fix_preview(
        self, *, queue_item_id: int, finding_id: str, patch: dict[str, Any], reviewer: str
    ) -> int:
        return await asyncio.to_thread(self._save_fix_preview, queue_item_id, finding_id, patch, reviewer)

    async def get_fix_preview(self, fix_id: int) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_fix_preview, fix_id)

    async def mark_fix_created(self, *, fix_id: int, reviewer: str, branch: str, url: str) -> None:
        await asyncio.to_thread(self._mark_fix_created, fix_id, reviewer, branch, url)

    async def mark_fix_failed(self, *, fix_id: int) -> None:
        await asyncio.to_thread(self._mark_fix_failed, fix_id)

    def _save_fix_preview(self, queue_item_id: int, finding_id: str, patch: dict[str, Any], reviewer: str) -> int:
        def operation(connection) -> int:
            _initialize_schema(connection)
            row = _run(connection, """
                INSERT INTO fix_prs (queue_item_id, finding_id, patch_json, reviewer, status)
                VALUES (%s, %s, %s, %s, 'previewed')
                ON CONFLICT (queue_item_id, finding_id) DO UPDATE SET
                    patch_json = EXCLUDED.patch_json, reviewer = EXCLUDED.reviewer,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
            """, (queue_item_id, finding_id, json.dumps(patch, separators=(",", ":")), reviewer))[0]
            _run(connection, "COMMIT")
            return int(row[0])
        return _execute(operation)

    def _get_fix_preview(self, fix_id: int) -> dict[str, Any] | None:
        def operation(connection) -> dict[str, Any] | None:
            _initialize_schema(connection)
            rows = _run(connection, """
                SELECT id, queue_item_id, finding_id, patch_json, reviewer, status,
                       branch, pull_request_url, created_at, updated_at
                FROM fix_prs WHERE id = %s
            """, (fix_id,))
            if not rows:
                return None
            fields = ("id", "queue_item_id", "finding_id", "patch", "reviewer", "status",
                      "branch", "pull_request_url", "created_at", "updated_at")
            values = list(rows[0])
            if isinstance(values[3], str):
                values[3] = json.loads(values[3])
            return dict(zip(fields, values, strict=True))
        return _execute(operation)

    def _mark_fix_created(self, fix_id: int, reviewer: str, branch: str, url: str) -> None:
        def operation(connection) -> None:
            _initialize_schema(connection)
            _run(connection, """
                UPDATE fix_prs SET reviewer = %s, status = 'created', branch = %s,
                    pull_request_url = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s
            """, (reviewer, branch, url, fix_id))
            _run(connection, "COMMIT")
        _execute(operation)

    def _mark_fix_failed(self, fix_id: int) -> None:
        def operation(connection) -> None:
            _initialize_schema(connection)
            _run(connection, "UPDATE fix_prs SET status = 'failed', updated_at = CURRENT_TIMESTAMP WHERE id = %s", (fix_id,))
            _run(connection, "COMMIT")
        _execute(operation)

    def _list_items(self, status: str, workspace_id: int | None = None) -> list[dict[str, Any]]:
        def operation(connection) -> list[dict[str, Any]]:
            _initialize_schema(connection)
            query = _SELECT_ITEM_SQL + " WHERE status = %s"
            params: tuple[Any, ...] = (status,)
            if workspace_id is not None:
                query += " AND workspace_id = %s"
                params += (workspace_id,)
            rows = _run(connection, query + " ORDER BY created_at ASC", params)
            return [_queue_item(row) for row in rows]

        return _execute(operation)

    def _get_item(self, queue_item_id: int, workspace_id: int | None = None) -> dict[str, Any] | None:
        def operation(connection) -> dict[str, Any] | None:
            _initialize_schema(connection)
            query = _SELECT_ITEM_SQL + " WHERE id = %s"
            params: tuple[Any, ...] = (queue_item_id,)
            if workspace_id is not None:
                query += " AND workspace_id = %s"
                params += (workspace_id,)
            rows = _run(connection, query, params)
            return _queue_item(rows[0]) if rows else None

        return _execute(operation)

    def _enqueue(self, **values: Any) -> int:
        def operation(connection) -> int:
            _initialize_schema(connection)
            row = _run(
                connection,
                """
                INSERT INTO review_queue
                    (workspace_id, delivery_id, repository, pr_number, head_sha,
                     review_payload_json, specialist_failures_json, status, reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending', %s)
                ON CONFLICT (workspace_id, repository, pr_number, head_sha)
                DO UPDATE SET
                    workspace_id = COALESCE(review_queue.workspace_id, EXCLUDED.workspace_id),
                    updated_at = review_queue.updated_at
                RETURNING id
                """,
                (
                    values.get("workspace_id"),
                    values["delivery_id"],
                    values["repository"],
                    values["pr_number"],
                    values["head_sha"],
                    json.dumps(values["review_payload"], separators=(",", ":")),
                    json.dumps(values["specialist_failures"], separators=(",", ":")),
                    values["reason"],
                ),
            )[0]
            _run(connection, "COMMIT")
            return int(row[0])

        return _execute(operation)

    def _record_decision(self, **values: Any) -> int:
        status = {
            "approve": "approved",
            "reject": "rejected",
            "edit": "edited",
        }.get(values["decision"])
        if status is None:
            raise ValueError("decision must be approve, reject, or edit")

        def operation(connection) -> int:
            _initialize_schema(connection)
            updated = _run(
                connection,
                """
                UPDATE review_queue
                SET updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND status = 'pending'
                RETURNING id, review_payload_json, repository, pr_number, head_sha
                """,
                (values["queue_item_id"],),
            )
            if not updated:
                raise RuntimeError("review queue item is missing or already resolved")
            queue_id, stored_payload, repository, pr_number, head_sha = updated[0]
            row = _run(
                connection,
                """
                INSERT INTO review_decisions
                    (queue_item_id, decision, edited_review_json, reviewer, comment)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    values["queue_item_id"],
                    values["decision"],
                    json.dumps(values["edited_review"], separators=(",", ":"))
                    if values["edited_review"] is not None
                    else None,
                    values["reviewer"],
                    values["comment"],
                ),
            )[0]
            _run(
                connection,
                """
                UPDATE review_queue
                SET status = %s, updated_at = CURRENT_TIMESTAMP,
                    resolved_at = CURRENT_TIMESTAMP, resolved_by = %s
                WHERE id = %s AND status = 'pending'
                """,
                (status, values["reviewer"], values["queue_item_id"]),
            )
            original_payload = _json_object(stored_payload)
            review_payload = (
                values["edited_review"]
                if values["decision"] == "edit"
                else original_payload.get("review", original_payload)
            )
            _insert_outcome_examples(
                connection,
                repository=repository,
                pr_number=int(pr_number),
                head_sha=head_sha,
                findings=_findings_from_review(review_payload),
                final_outcome=status,
                reviewer=values["reviewer"],
                source_queue_item_id=int(queue_id),
            )
            _run(connection, "COMMIT")
            return int(row[0])

        return _execute(operation)

    def _record_automatic_decision(self, **values: Any) -> int:
        def operation(connection) -> int:
            _initialize_schema(connection)
            row = _run(
                connection,
                """
                INSERT INTO review_outcomes
                    (delivery_id, repository, pr_number, head_sha,
                     outcome, review_payload_json, reason)
                VALUES (%s, %s, %s, %s, 'auto_post', %s, %s)
                ON CONFLICT (repository, pr_number, head_sha)
                DO UPDATE SET updated_at = CURRENT_TIMESTAMP
                RETURNING id
                """,
                (
                    values["delivery_id"],
                    values["repository"],
                    values["pr_number"],
                    values["head_sha"],
                    json.dumps(values["review_payload"], separators=(",", ":")),
                    values["reason"],
                ),
                )[0]
            _insert_outcome_examples(
                connection,
                repository=values["repository"],
                pr_number=values["pr_number"],
                head_sha=values["head_sha"],
                findings=_findings_from_review(values["review_payload"]),
                final_outcome="auto_post",
            )
            _run(connection, "COMMIT")
            return int(row[0])

        return _execute(operation)


    def _record_external_outcome(self, **values: Any) -> int:
        if values["final_outcome"] not in {"dismissed", "resolved"}:
            raise ValueError("external outcome must be dismissed or resolved")

        def operation(connection) -> int:
            _initialize_schema(connection)
            rows = _run(
                connection,
                """
                INSERT INTO outcome_examples (
                    repository, pr_number, head_sha, finding_id, category,
                    finding_json, final_outcome, source_queue_item_id,
                    source_review_run_id
                )
                SELECT repository, pr_number, head_sha, finding_id, category,
                       finding_json, %s, source_queue_item_id,
                       source_review_run_id
                FROM (
                    SELECT DISTINCT ON (finding_id)
                           repository, pr_number, head_sha, finding_id,
                           category, finding_json, source_queue_item_id,
                           source_review_run_id
                    FROM outcome_examples
                    WHERE repository = %s AND pr_number = %s
                      AND head_sha = %s
                      AND final_outcome IN ('auto_post', 'approved', 'edited')
                    ORDER BY finding_id, created_at DESC
                ) existing
                ON CONFLICT (repository, pr_number, head_sha, finding_id, final_outcome)
                DO NOTHING
                RETURNING id
                """,
                (
                    values["final_outcome"],
                    values["repository"],
                    values["pr_number"],
                    values["head_sha"],
                ),
            )
            _run(connection, "COMMIT")
            return len(rows)

        return _execute(operation)


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    return value if isinstance(value, dict) else {}


def _findings_from_review(review: Any) -> list[dict[str, Any]]:
    payload = _json_object(review)
    findings = payload.get("findings", [])
    return [finding for finding in findings if isinstance(finding, dict)]


def _insert_outcome_examples(
    connection: Any,
    *,
    repository: str,
    pr_number: int,
    head_sha: str,
    findings: list[dict[str, Any]],
    final_outcome: str,
    reviewer: str | None = None,
    source_queue_item_id: int | None = None,
    source_review_run_id: str | None = None,
) -> None:
    """Persist one learning example per finding in the same DB transaction."""
    parsed = [Finding.model_validate(finding) for finding in findings]
    parsed = assign_finding_ids(
        parsed,
        repository=repository,
        pr_number=pr_number,
        head_sha=head_sha,
    )
    for finding in parsed:
        _run(
            connection,
            """
            INSERT INTO outcome_examples (
                repository, pr_number, head_sha, finding_id, category,
                finding_json, final_outcome, reviewer,
                source_queue_item_id, source_review_run_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (repository, pr_number, head_sha, finding_id, final_outcome)
            DO UPDATE SET
                finding_json = EXCLUDED.finding_json,
                reviewer = COALESCE(EXCLUDED.reviewer, outcome_examples.reviewer)
            """,
            (
                repository,
                pr_number,
                head_sha,
                finding.finding_id,
                finding.category,
                json.dumps(finding.model_dump(exclude_none=True), separators=(",", ":")),
                final_outcome,
                reviewer,
                source_queue_item_id,
                source_review_run_id,
            ),
        )


_SELECT_ITEM_SQL = """
    SELECT id, workspace_id, delivery_id, repository, pr_number, head_sha,
           review_payload_json, specialist_failures_json, status, reason,
           created_at, updated_at, resolved_at, resolved_by,
           COALESCE((
               SELECT jsonb_agg(jsonb_build_object(
                   'finding_id', finding_id,
                   'status', status,
                   'pull_request_url', pull_request_url,
                   'branch', branch
               ) ORDER BY updated_at DESC)
               FROM fix_prs WHERE queue_item_id = review_queue.id
           ), '[]'::jsonb) AS fix_prs
    FROM review_queue
"""

# SQLSTATEs that indicate the session was dropped or reset beneath us (most
# commonly Neon's transaction-mode pooler recycling a connection, which breaks
# pg8000's extended-protocol prepared statements). Class 08 = connection
# exception, 57P01/57P02 = admin shutdown / crash, 26000 = prepared statement
# gone. A single reconnect clears these because every operation opens a fresh
# connection anyway.
_STALE_SQLSTATES = frozenset(
    {"26000", "08000", "08001", "08003", "08004", "08006", "08P01", "57P01", "57P02"}
)


def _is_stale_session(exc: BaseException) -> bool:
    if isinstance(exc, (PGInterfaceError, OSError, TimeoutError)):
        return True
    if isinstance(exc, PGDatabaseError):
        detail = exc.args[0] if exc.args and isinstance(exc.args[0], dict) else {}
        return detail.get("C") in _STALE_SQLSTATES
    return False


def _execute(operation: Callable[[Any], Any]) -> Any:
    """Run one DB operation, retrying with fresh connections.

    Every operation builds its own short-lived connection, so a stale session
    is always recovered simply by reconnecting. An operation that genuinely
    failed is never duplicated: the first attempt either never executed on the
    server (prepared-statement desync) or raised a connection-level error.
    """
    # A transaction-pooler can hand out more than one backend with reset
    # unnamed-statement state while it is recycling connections. Retry a few
    # fresh sessions before surfacing a genuine database failure.
    for attempt in range(3):
        connection = _connect()
        try:
            return operation(connection)
        except Exception as exc:
            if attempt == 2 or not _is_stale_session(exc):
                raise
            _LOG.warning(
                "db session recycled, reconnecting (attempt %d): %s",
                attempt + 1,
                exc,
            )
            time.sleep(0.1 * (attempt + 1))
        finally:
            # A transaction pooler can close the underlying socket after the
            # operation has committed. Cleanup must not mask that successful
            # result (or hide the original database exception).
            try:
                connection.close()
            except Exception:
                _LOG.debug("Ignoring stale database connection during cleanup", exc_info=True)
    return None  # unreachable


def _connect():
    from pg8000.native import Connection

    parsed = urlparse(database_url())
    return Connection(
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        host=parsed.hostname,
        port=parsed.port or 5432,
        database=parsed.path.lstrip("/"),
        ssl_context=ssl.create_default_context(),
        timeout=10,
    )


def _queue_item(row: list[Any]) -> dict[str, Any]:
    # Rows supplied by older callers/tests predate workspace_id. Database
    # reads use the new SELECT shape, but accept the old shape during rollout.
    if len(row) <= 13:
        legacy_fields = (
            "id", "delivery_id", "repository", "pr_number", "head_sha",
            "review_payload", "specialist_failures", "status", "reason",
            "created_at", "updated_at", "resolved_at", "resolved_by",
        )
        values = list(row)
        if len(values) < len(legacy_fields):
            values.extend([None] * (len(legacy_fields) - len(values)))
        item = dict(zip(legacy_fields, values, strict=False))
        item["workspace_id"] = None
        return item
    fields = (
        "id", "workspace_id", "delivery_id", "repository", "pr_number", "head_sha",
        "review_payload", "specialist_failures", "status", "reason",
        "created_at", "updated_at", "resolved_at", "resolved_by", "fix_prs",
    )
    # Older queue rows/databases may not include the nullable resolution
    # columns. Keep reads backward-compatible while the schema initializer
    # upgrades the table for future writes.
    values = list(row)
    if len(values) < len(fields):
        values.extend([None] * (len(fields) - len(values)))
    item = dict(zip(fields, values, strict=False))
    if isinstance(item.get("fix_prs"), str):
        try:
            item["fix_prs"] = json.loads(item["fix_prs"])
        except json.JSONDecodeError:
            item["fix_prs"] = []
    return item


def _initialize_schema(connection) -> None:
    _run(connection, "CREATE EXTENSION IF NOT EXISTS vector")
    _run(
        connection,
        """
        CREATE TABLE IF NOT EXISTS review_queue (
            id BIGSERIAL PRIMARY KEY,
            workspace_id BIGINT,
            delivery_id TEXT NOT NULL,
            repository TEXT NOT NULL,
            pr_number INTEGER NOT NULL,
            head_sha TEXT NOT NULL,
            review_payload_json JSONB NOT NULL,
            specialist_failures_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'approved', 'rejected', 'edited', 'expired')),
            reason TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMPTZ,
            resolved_by TEXT
        )
        """,
    )
    _run(connection, "ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS workspace_id BIGINT")
    _run(
        connection,
        "CREATE INDEX IF NOT EXISTS idx_review_queue_workspace_status ON review_queue(workspace_id, status)",
    )
    _run(
        connection,
        """
        CREATE TABLE IF NOT EXISTS review_outcomes (
            id BIGSERIAL PRIMARY KEY,
            delivery_id TEXT NOT NULL,
            repository TEXT NOT NULL,
            pr_number INTEGER NOT NULL,
            head_sha TEXT NOT NULL,
            outcome TEXT NOT NULL,
            review_payload_json JSONB NOT NULL,
            reason TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (repository, pr_number, head_sha)
        )
        """,
    )
    _run(
        connection,
        """
        DELETE FROM review_queue duplicate
        USING review_queue original
        WHERE duplicate.workspace_id IS NOT DISTINCT FROM original.workspace_id
          AND duplicate.repository = original.repository
          AND duplicate.pr_number = original.pr_number
          AND duplicate.head_sha = original.head_sha
          AND duplicate.id > original.id
        """,
    )
    _run(connection, "ALTER TABLE review_queue DROP CONSTRAINT IF EXISTS review_queue_repository_pr_number_head_sha_key")
    _run(connection, "DROP INDEX IF EXISTS uq_review_queue_pr_head")
    _run(
        connection,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_review_queue_workspace_pr_head
        ON review_queue(workspace_id, repository, pr_number, head_sha)
        """,
    )
    _run(
        connection,
        """
        CREATE TABLE IF NOT EXISTS review_decisions (
            id BIGSERIAL PRIMARY KEY,
            queue_item_id BIGINT NOT NULL REFERENCES review_queue(id) ON DELETE CASCADE,
            decision TEXT NOT NULL CHECK (decision IN ('approve', 'reject', 'edit')),
            edited_review_json JSONB,
            reviewer TEXT NOT NULL,
            comment TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
    )
    _run(connection, """
        CREATE TABLE IF NOT EXISTS fix_prs (
            id BIGSERIAL PRIMARY KEY,
            queue_item_id BIGINT NOT NULL REFERENCES review_queue(id) ON DELETE CASCADE,
            finding_id TEXT NOT NULL,
            patch_json JSONB NOT NULL,
            reviewer TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('previewed', 'created', 'failed')),
            branch TEXT,
            pull_request_url TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (queue_item_id, finding_id)
        )
    """)
    _run(
        connection,
        f"""
        CREATE TABLE IF NOT EXISTS outcome_examples (
            id BIGSERIAL PRIMARY KEY,
            repository TEXT NOT NULL,
            pr_number INTEGER NOT NULL,
            head_sha TEXT NOT NULL,
            finding_id TEXT NOT NULL,
            category TEXT NOT NULL,
            finding_json JSONB NOT NULL,
            final_outcome TEXT NOT NULL
                CHECK (final_outcome IN (
                    'auto_post', 'approved', 'edited',
                    'rejected', 'dismissed', 'resolved'
                )),
            reviewer TEXT,
            source_queue_item_id BIGINT,
            source_review_run_id TEXT,
            embedding_model TEXT,
            embedding vector({EMBEDDING_DIMENSIONS}),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (repository, pr_number, head_sha, finding_id, final_outcome)
        )
        """,
    )
    _run(
        connection,
        "CREATE INDEX IF NOT EXISTS idx_outcome_examples_category "
        "ON outcome_examples(category, final_outcome)",
    )
    _run(
        connection,
        "CREATE INDEX IF NOT EXISTS idx_outcome_examples_repository "
        "ON outcome_examples(repository, created_at DESC)",
    )
    _run(connection, "CREATE INDEX IF NOT EXISTS idx_review_queue_status ON review_queue(status)")
    _run(connection, "CREATE INDEX IF NOT EXISTS idx_review_queue_repository ON review_queue(repository)")
    _run(connection, "CREATE INDEX IF NOT EXISTS idx_review_queue_created_at ON review_queue(created_at)")


def _run(connection, query: str, parameters: tuple[Any, ...] = ()) -> list[list[Any]]:
    """Execute with PostgreSQL's simple-query protocol.

    The cloud database uses transaction pooling, which can route pg8000's
    extended-protocol Parse/Describe/Bind messages to different backends and
    produces SQLSTATE 26000. Values are encoded as strict SQL literals so the
    simple protocol remains safe while avoiding unnamed prepared statements.
    """
    values = iter(parameters)
    rendered = re.sub(r"%s", lambda _: _sql_literal(next(values)), query)
    try:
        next(values)
    except StopIteration:
        return connection.run(rendered)
    raise ValueError("query contains fewer placeholders than supplied parameters")


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float, Decimal)):
        return str(value)
    if isinstance(value, Vector):
        value = value.to_text()
    elif isinstance(value, (dict, list)):
        value = json.dumps(value, separators=(",", ":"))
    elif isinstance(value, (date, datetime)):
        value = value.isoformat()
    if not isinstance(value, str):
        raise TypeError(f"unsupported SQL parameter type: {type(value).__name__}")
    if "\x00" in value:
        raise ValueError("SQL parameters cannot contain NUL bytes")
    return "'" + value.replace("'", "''") + "'"
