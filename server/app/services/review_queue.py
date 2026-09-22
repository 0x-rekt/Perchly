import asyncio
import json
import logging
import re
import ssl
from typing import Any, Callable
from urllib.parse import unquote, urlparse

from pg8000.exceptions import DatabaseError as PGDatabaseError
from pg8000.exceptions import InterfaceError as PGInterfaceError

from app.core.config import database_url

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

    async def list_items(self, *, status: str = "pending") -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._list_items, status)

    async def get_item(self, queue_item_id: int) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_item, queue_item_id)

    def _list_items(self, status: str) -> list[dict[str, Any]]:
        def operation(connection) -> list[dict[str, Any]]:
            _initialize_schema(connection)
            rows = _run(
                connection,
                _SELECT_ITEM_SQL + " WHERE status = %s ORDER BY created_at ASC",
                (status,),
            )
            return [_queue_item(row) for row in rows]

        return _execute(operation)

    def _get_item(self, queue_item_id: int) -> dict[str, Any] | None:
        def operation(connection) -> dict[str, Any] | None:
            _initialize_schema(connection)
            rows = _run(
                connection,
                _SELECT_ITEM_SQL + " WHERE id = %s",
                (queue_item_id,),
            )
            return _queue_item(rows[0]) if rows else None

        return _execute(operation)

    def _enqueue(self, **values: Any) -> int:
        def operation(connection) -> int:
            _initialize_schema(connection)
            row = _run(
                connection,
                """
                INSERT INTO review_queue
                    (delivery_id, repository, pr_number, head_sha,
                     review_payload_json, specialist_failures_json, status, reason)
                VALUES (%s, %s, %s, %s, %s, %s, 'pending', %s)
                ON CONFLICT (repository, pr_number, head_sha)
                DO UPDATE SET updated_at = review_queue.updated_at
                RETURNING id
                """,
                (
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
                RETURNING id
                """,
                (values["queue_item_id"],),
            )
            if not updated:
                raise RuntimeError("review queue item is missing or already resolved")
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
            _run(connection, "COMMIT")
            return int(row[0])

        return _execute(operation)


_SELECT_ITEM_SQL = """
    SELECT id, delivery_id, repository, pr_number, head_sha,
           review_payload_json, specialist_failures_json, status, reason,
           created_at, updated_at, resolved_at, resolved_by
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
    """Run one DB operation, retrying once with a fresh connection.

    Every operation builds its own short-lived connection, so a stale session
    is always recovered simply by reconnecting. An operation that genuinely
    failed is never duplicated: the first attempt either never executed on the
    server (prepared-statement desync) or raised a connection-level error.
    """
    for attempt in range(2):
        connection = _connect()
        try:
            return operation(connection)
        except Exception as exc:
            if attempt == 1 or not _is_stale_session(exc):
                raise
            _LOG.warning(
                "db session recycled, reconnecting (attempt %d): %s",
                attempt + 1,
                exc,
            )
        finally:
            connection.close()
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
    fields = (
        "id", "delivery_id", "repository", "pr_number", "head_sha",
        "review_payload", "specialist_failures", "status", "reason",
        "created_at", "updated_at", "resolved_at", "resolved_by",
    )
    return dict(zip(fields, row, strict=True))


def _initialize_schema(connection) -> None:
    _run(
        connection,
        """
        CREATE TABLE IF NOT EXISTS review_queue (
            id BIGSERIAL PRIMARY KEY,
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
            resolved_by TEXT,
            UNIQUE (repository, pr_number, head_sha)
        )
        """,
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
        WHERE duplicate.repository = original.repository
          AND duplicate.pr_number = original.pr_number
          AND duplicate.head_sha = original.head_sha
          AND duplicate.id > original.id
        """,
    )
    _run(
        connection,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_review_queue_pr_head
        ON review_queue(repository, pr_number, head_sha)
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
    _run(connection, "CREATE INDEX IF NOT EXISTS idx_review_queue_status ON review_queue(status)")
    _run(connection, "CREATE INDEX IF NOT EXISTS idx_review_queue_repository ON review_queue(repository)")
    _run(connection, "CREATE INDEX IF NOT EXISTS idx_review_queue_created_at ON review_queue(created_at)")


def _run(connection, query: str, parameters: tuple[Any, ...] = ()) -> list[list[Any]]:
    names = iter(f"param_{index}" for index in range(len(parameters)))
    for_values = {}
    import re

    query = re.sub(r"%s", lambda _: f":{next(names)}", query)
    for index, value in enumerate(parameters):
        for_values[f"param_{index}"] = value
    return connection.run(query, **for_values)
