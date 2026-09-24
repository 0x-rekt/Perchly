import asyncio
import logging
import re
import ssl
import time
from decimal import Decimal
from urllib.parse import unquote, urlparse
from dataclasses import dataclass

from google import genai
from google.genai import types
from pg8000.exceptions import DatabaseError as PGDatabaseError
from pg8000.exceptions import InterfaceError as PGInterfaceError
from pgvector import Vector

from app.core.config import (
    EMBEDDING_DIMENSIONS,
    GEMINI_EMBEDDING_MODEL,
    RETRIEVAL_TOP_K,
    database_url,
    gemini_api_key,
)
from app.core.pricing import calculate_cost
from app.schemas.findings import FindingCategory
from app.services.github_api import RepositoryFile
from app.services.telemetry import ReviewContext, otel_span

logger = logging.getLogger(__name__)

_HUNK_HEADER = re.compile(r"^@@ -(?:\d+)(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
_FILE_HEADER = re.compile(r"^diff --git a/(.*?) b/(.*?)$")
_MAX_CHUNK_CHARACTERS = 6_000

SPECIALIST_QUERIES: dict[FindingCategory, str] = {
    "security": "security vulnerabilities, secrets, authentication, authorization, injection, unsafe data handling",
    "quality": "code quality, complexity, duplication, maintainability, and changed code patterns",
    "test_coverage": "tests, changed behavior, branches, edge cases, and missing test coverage",
    "docs": "documentation, public APIs, docstrings, README, configuration, and user-facing behavior",
}


@dataclass(frozen=True)
class CodeChunk:
    path: str
    line_start: int
    line_end: int
    content: str


def chunk_file_content(path: str, content: str) -> list[CodeChunk]:
    """Split a full repository file into bounded, line-addressable chunks."""
    lines = content.splitlines()
    chunks: list[CodeChunk] = []
    start = 0
    while start < len(lines):
        end = start
        characters = 0
        while end < len(lines) and (
            end == start or characters + len(lines[end]) + 1 <= _MAX_CHUNK_CHARACTERS
        ):
            characters += len(lines[end]) + 1
            end += 1
        chunks.append(
            CodeChunk(
                path=path,
                line_start=start + 1,
                line_end=end,
                content="\n".join(lines[start:end]),
            )
        )
        start = end
    return chunks


def chunk_changed_files(diff: str) -> list[CodeChunk]:
    """Split a unified diff into bounded chunks, retaining new-file line locations."""
    chunks: list[CodeChunk] = []
    current_path: str | None = None
    current_lines: list[str] = []
    current_start = 1
    current_line = 1

    def flush() -> None:
        nonlocal current_lines, current_start
        if not current_path or not current_lines:
            current_lines = []
            return
        content = "\n".join(current_lines).strip()
        if content:
            chunks.append(
                CodeChunk(
                    path=current_path,
                    line_start=current_start,
                    line_end=max(current_start, current_line - 1),
                    content=content,
                )
            )
        current_lines = []

    for line in diff.splitlines():
        file_match = _FILE_HEADER.match(line)
        if file_match:
            flush()
            current_path = file_match.group(2)
            current_line = 1
            continue

        hunk_match = _HUNK_HEADER.match(line)
        if hunk_match:
            flush()
            current_start = int(hunk_match.group(1))
            current_line = current_start
            continue

        if not current_path or not current_line:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            current_lines.append(line[1:])
            current_line += 1
        elif line.startswith(" "):
            current_lines.append(line[1:])
            current_line += 1
        elif line.startswith("-") and not line.startswith("---"):
            continue

        if sum(len(item) + 1 for item in current_lines) >= _MAX_CHUNK_CHARACTERS:
            flush()
            current_start = current_line

    flush()
    return chunks


class RetrievalService:
    """Persist changed code in cloud PostgreSQL and retrieve category-specific context."""

    async def build_contexts(
        self,
        *,
        repository: str,
        head_sha: str,
        diff: str,
        repository_files: list[RepositoryFile] | None = None,
        telemetry_ctx: ReviewContext | None = None,
    ) -> dict[FindingCategory, str]:
        chunks = [
            chunk
            for repository_file in repository_files or []
            for chunk in chunk_file_content(repository_file.path, repository_file.content)
        ]
        if not chunks:
            chunks = chunk_changed_files(diff)
        if not chunks:
            return {category: "" for category in SPECIALIST_QUERIES}
        return await asyncio.to_thread(
            self._build_contexts,
            repository=repository,
            head_sha=head_sha,
            chunks=chunks,
            telemetry_ctx=telemetry_ctx,
        )

    def _build_contexts(
        self,
        *,
        repository: str,
        head_sha: str,
        chunks: list[CodeChunk],
        telemetry_ctx: ReviewContext | None = None,
    ) -> dict[FindingCategory, str]:
        with otel_span(
            "perchly.tool.retrieval_database",
            attributes={
                "perchly.review_run_id": telemetry_ctx.review_run_id if telemetry_ctx else "",
                "perchly.repository": repository,
                "perchly.head_sha": head_sha,
                "perchly.phase": "retrieval",
                "perchly.span_type": "tool_call",
                "perchly.retrieval.chunk_count": len(chunks),
            },
        ):
            return self._build_contexts_operation(
                repository=repository,
                head_sha=head_sha,
                chunks=chunks,
                telemetry_ctx=telemetry_ctx,
            )

    def _build_contexts_operation(
        self,
        *,
        repository: str,
        head_sha: str,
        chunks: list[CodeChunk],
        telemetry_ctx: ReviewContext | None = None,
    ) -> dict[FindingCategory, str]:
        from pgvector.pg8000 import register_vector

        client = genai.Client(api_key=gemini_api_key())
        embeddings = _embed(client, [chunk.content for chunk in chunks], telemetry_ctx=telemetry_ctx)

        # Neon transaction-pooler sessions can recycle an unnamed prepared
        # statement between commands (SQLSTATE 26000). A fresh connection is
        # required; allow a few attempts because the pooler can hand out more
        # than one stale backend in succession.
        for attempt in range(3):
            connection = _connect()
            try:
                register_vector(connection)
                _initialize_schema(connection)
                repository_id = _upsert_repository(connection, repository)
                _store_chunks(
                    connection,
                    repository_id=repository_id,
                    head_sha=head_sha,
                    chunks=chunks,
                    embeddings=embeddings,
                )
                contexts: dict[FindingCategory, str] = {}
                for category, query in SPECIALIST_QUERIES.items():
                    query_embedding = _embed(client, [query], telemetry_ctx=telemetry_ctx)[0]
                    contexts[category] = _retrieve_category_context(
                        connection,
                        repository_id=repository_id,
                        head_sha=head_sha,
                        category=category,
                        query_embedding=Vector(query_embedding),
                    )
                _run(connection, "COMMIT")
                return contexts
            except Exception as exc:
                if attempt == 2 or not _is_stale_session(exc):
                    raise
                logger.warning(
                    "db session recycled during retrieval, reconnecting (attempt %d): %s",
                    attempt + 1,
                    exc,
                )
                time.sleep(0.15 * (attempt + 1))
            finally:
                connection.close()
        return {}  # unreachable


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


# SQLSTATEs produced when Neon's transaction-mode pooler recycles a session
# (dropping pg8000's extended-protocol prepared statements mid-activity):
# class 08 = connection exception, 26000 = prepared statement gone.
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


def _embed(
    client: genai.Client,
    contents: list[str],
    telemetry_ctx: ReviewContext | None = None,
) -> list[list[float]]:
    ctx = telemetry_ctx if telemetry_ctx is not None else ReviewContext()
    embeddings: list[list[float]] = []
    for content in contents:
        t0 = time.monotonic()
        try:
            with otel_span(
                "perchly.llm.embed_content",
                attributes={
                    "perchly.review_run_id": ctx.review_run_id,
                    "perchly.repository": ctx.repository,
                    "perchly.pr_number": ctx.pr_number,
                    "perchly.head_sha": ctx.head_sha,
                    "perchly.agent": ctx.agent,
                    "perchly.phase": "retrieval",
                    "perchly.span_type": "llm_call",
                    "gen_ai.system": "gemini",
                    "gen_ai.request.model": GEMINI_EMBEDDING_MODEL,
                },
            ) as otel:
                response = client.models.embed_content(
                    model=GEMINI_EMBEDDING_MODEL,
                    contents=content,
                    config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIMENSIONS),
                )
                usage = getattr(response, "usage_metadata", None)
                otel.set_attribute(
                    "gen_ai.usage.input_tokens",
                    getattr(usage, "prompt_token_count", 0) or 0,
                )
        except Exception as exc:
            _emit_embedding_span(
                ctx,
                latency_ms=int((time.monotonic() - t0) * 1000),
                tokens_in=0,
                content=content,
                status="failed",
                error_message=str(exc),
            )
            raise
        latency_ms = int((time.monotonic() - t0) * 1000)
        usage = getattr(response, "usage_metadata", None)
        tokens_in = getattr(usage, "prompt_token_count", 0) or 0
        cost = calculate_cost(model=GEMINI_EMBEDDING_MODEL, tokens_in=tokens_in)
        _emit_embedding_span(
            ctx,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            cost_usd=cost,
            content=content,
        )
        returned = response.embeddings or []
        if len(returned) != 1:
            raise RuntimeError(
                f"Embedding service returned {len(returned)} vectors for one input "
                f"using {GEMINI_EMBEDDING_MODEL}"
            )
        embedding = list(returned[0].values or [])
        if len(embedding) != EMBEDDING_DIMENSIONS:
            raise RuntimeError(
                f"Embedding service returned dimension {len(embedding)}; "
                f"expected {EMBEDDING_DIMENSIONS} using {GEMINI_EMBEDDING_MODEL}"
            )
        embeddings.append(embedding)
    return embeddings


def _emit_embedding_span(
    ctx: ReviewContext,
    *,
    latency_ms: int,
    tokens_in: int,
    content: str,
    cost_usd: Decimal | float | None = None,
    status: str = "success",
    error_message: str | None = None,
) -> None:
    """Fire-and-forget embedding span write – runs inside the thread."""
    try:
        from app.services.telemetry import emit_span

        emit_span(
            review_run_id=ctx.review_run_id,
            repository=ctx.repository,
            pr_number=ctx.pr_number,
            head_sha=ctx.head_sha,
            agent=ctx.agent,
            phase="retrieval",
            span_type="llm_call",
            model=GEMINI_EMBEDDING_MODEL,
            tokens_in=tokens_in,
            tokens_out=0,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            input_summary=content[:500],
            status=status,
            error_message=error_message,
        )
    except Exception:
        pass


def _initialize_schema(connection) -> None:
    _run(connection, "CREATE EXTENSION IF NOT EXISTS vector")
    _run(connection,
        """
        CREATE TABLE IF NOT EXISTS repositories (
            id BIGSERIAL PRIMARY KEY,
            full_name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    _run(connection,
        f"""
        CREATE TABLE IF NOT EXISTS code_chunks (
            id BIGSERIAL PRIMARY KEY,
            repository_id BIGINT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
            head_sha TEXT NOT NULL,
            path TEXT NOT NULL,
            line_start INTEGER NOT NULL,
            line_end INTEGER NOT NULL,
            content TEXT NOT NULL,
            embedding_model TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(repository_id, head_sha, path, line_start, line_end)
        )
        """,
    )
    _run(connection, "ALTER TABLE code_chunks DROP COLUMN IF EXISTS embedding")
    _run(connection,
        f"""
        CREATE TABLE IF NOT EXISTS embeddings (
            chunk_id BIGINT PRIMARY KEY REFERENCES code_chunks(id) ON DELETE CASCADE,
            vector vector({EMBEDDING_DIMENSIONS}) NOT NULL,
            model TEXT NOT NULL
        )
        """,
    )
    _run(connection,
        """
        CREATE TABLE IF NOT EXISTS review_context (
            id BIGSERIAL PRIMARY KEY,
            repository_id BIGINT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
            head_sha TEXT NOT NULL,
            category TEXT NOT NULL,
            chunk_id BIGINT NOT NULL REFERENCES code_chunks(id) ON DELETE CASCADE,
            rank INTEGER NOT NULL,
            similarity REAL NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(repository_id, head_sha, category, chunk_id)
        )
        """
    )


def _upsert_repository(connection, full_name: str) -> int:
    row = _run(connection,
        """
        INSERT INTO repositories (full_name) VALUES (%s)
        ON CONFLICT (full_name) DO UPDATE SET full_name = EXCLUDED.full_name
        RETURNING id
        """,
        (full_name,),
    )[0]
    return int(row[0])


def _store_chunks(connection, *, repository_id: int, head_sha: str, chunks: list[CodeChunk], embeddings: list[list[float]]) -> list[int]:
    chunk_ids: list[int] = []
    for chunk, embedding in zip(chunks, embeddings, strict=True):
        row = _run(connection,
            """
            INSERT INTO code_chunks
                (repository_id, head_sha, path, line_start, line_end, content, embedding_model)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (repository_id, head_sha, path, line_start, line_end)
            DO UPDATE SET content = EXCLUDED.content,
                          embedding_model = EXCLUDED.embedding_model
            RETURNING id
            """,
            (
                repository_id,
                head_sha,
                chunk.path,
                chunk.line_start,
                chunk.line_end,
                chunk.content,
                GEMINI_EMBEDDING_MODEL,
            ),
        )[0]
        chunk_id = int(row[0])
        _run(connection,
            """
            INSERT INTO embeddings (chunk_id, vector, model) VALUES (%s, %s, %s)
            ON CONFLICT (chunk_id) DO UPDATE SET vector = EXCLUDED.vector, model = EXCLUDED.model
            """,
            (chunk_id, Vector(embedding), GEMINI_EMBEDDING_MODEL),
        )
        chunk_ids.append(chunk_id)
    return chunk_ids


def _retrieve_category_context(
    connection,
    *,
    repository_id: int,
    head_sha: str,
    category: FindingCategory,
    query_embedding: list[float],
) -> str:
    _run(connection,
        "DELETE FROM review_context WHERE repository_id = %s AND head_sha = %s AND category = %s",
        (repository_id, head_sha, category),
    )
    rows = _run(connection,
        """
         SELECT code_chunks.id, path, line_start, line_end, content,
             1 - (embeddings.vector <=> %s) AS similarity
        FROM code_chunks
         JOIN embeddings ON embeddings.chunk_id = code_chunks.id
        WHERE repository_id = %s
         ORDER BY embeddings.vector <=> %s
        LIMIT %s
        """,
        (query_embedding, repository_id, query_embedding, RETRIEVAL_TOP_K),
    )
    parts: list[str] = []
    for rank, row in enumerate(rows, start=1):
        chunk_id, path, line_start, line_end, content, similarity = row
        _run(connection,
            """
            INSERT INTO review_context
                (repository_id, head_sha, category, chunk_id, rank, similarity)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (repository_id, head_sha, category, chunk_id)
            DO UPDATE SET rank = EXCLUDED.rank, similarity = EXCLUDED.similarity
            """,
            (repository_id, head_sha, category, chunk_id, rank, similarity),
        )
        parts.append(f"{path}:{line_start}-{line_end}\n{content}")
    return "\n\n".join(parts)


def _run(connection, query: str, parameters: tuple[object, ...] = ()) -> list[tuple]:
    """Run positional SQL through pg8000's named-parameter API."""
    parameter_names = (f"param_{index}" for index in range(len(parameters)))
    parameter_names = iter(parameter_names)
    query = re.sub(r"%s", lambda _: f":{next(parameter_names)}", query)
    values = {
        f"param_{index}": value for index, value in enumerate(parameters)
    }
    return connection.run(query, **values)
