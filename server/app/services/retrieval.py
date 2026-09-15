import asyncio
import re
import ssl
from urllib.parse import unquote, urlparse
from dataclasses import dataclass

from google import genai
from google.genai import types
from pgvector import Vector

from app.core.config import (
    EMBEDDING_DIMENSIONS,
    GEMINI_EMBEDDING_MODEL,
    RETRIEVAL_TOP_K,
    database_url,
    gemini_api_key,
)
from app.schemas.findings import FindingCategory

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
    """Persist changed code in Neon and retrieve category-specific context."""

    async def build_contexts(
        self, *, repository: str, head_sha: str, diff: str
    ) -> dict[FindingCategory, str]:
        chunks = chunk_changed_files(diff)
        if not chunks:
            return {category: "" for category in SPECIALIST_QUERIES}
        return await asyncio.to_thread(
            self._build_contexts,
            repository=repository,
            head_sha=head_sha,
            chunks=chunks,
        )

    def _build_contexts(
        self, *, repository: str, head_sha: str, chunks: list[CodeChunk]
    ) -> dict[FindingCategory, str]:
        from pgvector.pg8000 import register_vector
        from pg8000.native import Connection

        client = genai.Client(api_key=gemini_api_key())
        embeddings = _embed(client, [chunk.content for chunk in chunks])
        parsed_url = urlparse(database_url())
        connection = Connection(
            user=unquote(parsed_url.username or ""),
            password=unquote(parsed_url.password or ""),
            host=parsed_url.hostname,
            port=parsed_url.port or 5432,
            database=parsed_url.path.lstrip("/"),
            ssl_context=ssl.create_default_context(),
            timeout=10,
        )
        try:
            register_vector(connection)
            _initialize_schema(connection)
            repository_id = _upsert_repository(connection, repository)
            chunk_ids = _store_chunks(
                connection,
                repository_id=repository_id,
                head_sha=head_sha,
                chunks=chunks,
                embeddings=embeddings,
            )
            contexts: dict[FindingCategory, str] = {}
            for category, query in SPECIALIST_QUERIES.items():
                query_embedding = _embed(client, [query])[0]
                contexts[category] = _retrieve_category_context(
                    connection,
                    repository_id=repository_id,
                    head_sha=head_sha,
                    category=category,
                    query_embedding=Vector(query_embedding),
                    chunk_ids=chunk_ids,
                )
            _run(connection, "COMMIT")
            return contexts
        finally:
            connection.close()


def _embed(client: genai.Client, contents: list[str]) -> list[list[float]]:
    embeddings: list[list[float]] = []
    for content in contents:
        response = client.models.embed_content(
            model=GEMINI_EMBEDDING_MODEL,
            contents=content,
            config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIMENSIONS),
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
            embedding vector({EMBEDDING_DIMENSIONS}) NOT NULL,
            embedding_model TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(repository_id, head_sha, path, line_start, line_end)
        )
        """,
    )
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
                (repository_id, head_sha, path, line_start, line_end, content, embedding, embedding_model)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (repository_id, head_sha, path, line_start, line_end)
            DO UPDATE SET content = EXCLUDED.content, embedding = EXCLUDED.embedding,
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
                Vector(embedding),
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
    chunk_ids: list[int],
) -> str:
    _run(connection,
        "DELETE FROM review_context WHERE repository_id = %s AND head_sha = %s AND category = %s",
        (repository_id, head_sha, category),
    )
    rows = _run(connection,
        """
        SELECT id, path, line_start, line_end, content,
               1 - (embedding <=> %s) AS similarity
        FROM code_chunks
        WHERE repository_id = %s AND head_sha = %s AND id = ANY(%s)
        ORDER BY embedding <=> %s
        LIMIT %s
        """,
        (query_embedding, repository_id, head_sha, chunk_ids, query_embedding, RETRIEVAL_TOP_K),
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