"""Embedding and similarity search for Phase 5 outcome examples."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from google import genai
from pgvector import Vector

from app.core.config import GEMINI_EMBEDDING_MODEL, gemini_api_key
from app.schemas.findings import Finding
from app.services.retrieval import _embed
from app.services.review_queue import _execute, _initialize_schema, _run
from app.services.telemetry import ReviewContext

logger = logging.getLogger(__name__)


def outcome_example_text(finding: Finding | dict[str, Any], outcome: str) -> str:
    """Create a compact, stable text representation for embedding."""
    value = finding.model_dump(exclude_none=True) if isinstance(finding, Finding) else finding
    return "\n".join(
        (
            f"category: {value.get('category', '')}",
            f"severity: {value.get('severity', '')}",
            f"file: {value.get('file', '')}",
            f"lines: {value.get('line_start', '')}-{value.get('line_end', '')}",
            f"message: {value.get('message', '')}",
            f"suggested_fix: {value.get('suggested_fix', '')}",
            f"outcome: {outcome}",
        )
    )


def _pending_examples(limit: int) -> list[dict[str, Any]]:
    def operation(connection) -> list[dict[str, Any]]:
        _initialize_schema(connection)
        rows = _run(
            connection,
            """
            SELECT id, repository, pr_number, head_sha,
                   finding_json, final_outcome
            FROM outcome_examples
            WHERE embedding IS NULL
            ORDER BY id
            LIMIT %s
            """,
            (limit,),
        )
        return [
            {
                "id": int(row[0]),
                "repository": row[1],
                "pr_number": int(row[2]),
                "head_sha": row[3],
                "finding": json.loads(row[4]) if isinstance(row[4], str) else row[4],
                "outcome": row[5],
            }
            for row in rows
        ]

    return _execute(operation)


def _store_embedding(example_id: int, embedding: list[float]) -> None:
    def operation(connection) -> None:
        from pgvector.pg8000 import register_vector

        register_vector(connection)
        _run(
            connection,
            """
            UPDATE outcome_examples
            SET embedding = %s, embedding_model = %s
            WHERE id = %s AND embedding IS NULL
            """,
            (Vector(embedding), GEMINI_EMBEDDING_MODEL, example_id),
        )
        _run(connection, "COMMIT")

    _execute(operation)


async def embed_pending_outcomes(*, limit: int = 20) -> int:
    """Embed pending examples; failures are logged and do not fail reviews."""
    try:
        examples = await asyncio.to_thread(_pending_examples, max(1, min(limit, 100)))
        client = genai.Client(api_key=gemini_api_key())
    except Exception:
        logger.warning("Could not load outcome examples for embedding", exc_info=True)
        return 0
    if not examples:
        return 0

    embedded = 0
    for example in examples:
        try:
            context = ReviewContext(
                review_run_id="outcome-example",
                repository=example["repository"],
                pr_number=example["pr_number"],
                head_sha=example["head_sha"],
                agent="outcome_retrieval",
            )
            vector = await asyncio.to_thread(
                _embed,
                client,
                [outcome_example_text(example["finding"], example["outcome"])],
                context,
            )
            await asyncio.to_thread(_store_embedding, example["id"], vector[0])
            embedded += 1
        except Exception:
            logger.warning(
                "Could not embed outcome example id=%s",
                example["id"],
                exc_info=True,
            )
    return embedded


async def find_similar_outcomes(
    *,
    repository: str,
    category: str,
    finding: Finding | dict[str, Any],
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return nearest historical examples for a category in a repository."""
    client = genai.Client(api_key=gemini_api_key())
    context = ReviewContext(repository=repository, agent="outcome_retrieval")
    vector = await asyncio.to_thread(
        _embed,
        client,
        [outcome_example_text(finding, "query")],
        context,
    )

    def operation(connection) -> list[dict[str, Any]]:
        from pgvector.pg8000 import register_vector

        register_vector(connection)
        rows = _run(
            connection,
            """
            SELECT id, finding_json, final_outcome,
                   1 - (embedding <=> %s) AS similarity
            FROM outcome_examples
            WHERE repository = %s AND category = %s AND embedding IS NOT NULL
            ORDER BY embedding <=> %s
            LIMIT %s
            """,
            (Vector(vector[0]), repository, category, Vector(vector[0]), limit),
        )
        return [
            {
                "id": int(row[0]),
                "finding": json.loads(row[1]) if isinstance(row[1], str) else row[1],
                "outcome": row[2],
                "similarity": float(row[3]),
            }
            for row in rows
        ]

    return await asyncio.to_thread(_execute, operation)
