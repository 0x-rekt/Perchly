import os
import ssl
import uuid
from urllib.parse import unquote, urlparse

import pytest
from dotenv import load_dotenv

from app.core.config import EMBEDDING_DIMENSIONS, GEMINI_EMBEDDING_MODEL
from app.services.retrieval import CodeChunk, RetrievalService, _run


def _cloud_postgres_connection():
    from pg8000.native import Connection

    parsed = urlparse(os.environ["DATABASE_URL"])
    return Connection(
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        host=parsed.hostname,
        port=parsed.port or 5432,
        database=parsed.path.lstrip("/"),
        ssl_context=ssl.create_default_context(),
        timeout=15,
    )


@pytest.mark.integration
def test_cloud_postgres_retrieval_round_trip() -> None:
    load_dotenv()
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("Set RUN_POSTGRES_INTEGRATION=1 to run the live integration test")
    if not os.getenv("DATABASE_URL") or not os.getenv("GEMINI_API_KEY"):
        pytest.skip("Requires DATABASE_URL and GEMINI_API_KEY for cloud PostgreSQL integration")

    from pgvector.pg8000 import register_vector

    repository = f"perchly-integration/{uuid.uuid4().hex}"
    head_sha = f"integration-{uuid.uuid4().hex}"
    chunks = [
        CodeChunk(
            path="src/security.py",
            line_start=1,
            line_end=3,
            content="def load_token():\n    return os.environ['SERVICE_TOKEN']\n",
        )
    ]
    connection = _cloud_postgres_connection()
    try:
        register_vector(connection)
        contexts = RetrievalService()._build_contexts(
            repository=repository,
            head_sha=head_sha,
            chunks=chunks,
        )

        extension = _run(
            connection,
            "SELECT 1 FROM pg_extension WHERE extname = %s",
            ("vector",),
        )
        assert extension and extension[0][0] == 1

        tables = _run(
            connection,
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = ANY(%s)
            ORDER BY table_name
            """,
            (["repositories", "code_chunks", "embeddings", "review_context"],),
        )
        assert [row[0] for row in tables] == [
            "code_chunks",
            "embeddings",
            "repositories",
            "review_context",
        ]

        stored = _run(
            connection,
            """
            SELECT embeddings.chunk_id, embeddings.vector, embeddings.model,
                   vector_dims(embeddings.vector)
            FROM embeddings
            JOIN code_chunks ON code_chunks.id = embeddings.chunk_id
            JOIN repositories ON repositories.id = code_chunks.repository_id
            WHERE repositories.full_name = %s AND code_chunks.head_sha = %s
            """,
            (repository, head_sha),
        )
        assert len(stored) == 1
        chunk_id, vector, model, dimensions = stored[0]
        assert model == GEMINI_EMBEDDING_MODEL
        assert dimensions == EMBEDDING_DIMENSIONS

        nearest = _run(
            connection,
            """
            SELECT chunk_id, vector <=> %s AS distance
            FROM embeddings
            WHERE chunk_id = %s
            ORDER BY vector <=> %s
            LIMIT 1
            """,
            (vector, chunk_id, vector),
        )
        assert nearest[0][0] == chunk_id
        assert float(nearest[0][1]) == pytest.approx(0.0, abs=1e-6)
        assert all(contexts.values())
    finally:
        _run(
            connection,
            """
            DELETE FROM review_context
            WHERE repository_id IN (SELECT id FROM repositories WHERE full_name = %s)
            """,
            (repository,),
        )
        _run(
            connection,
            """
            DELETE FROM embeddings
            WHERE chunk_id IN (
                SELECT code_chunks.id
                FROM code_chunks JOIN repositories ON repositories.id = code_chunks.repository_id
                WHERE repositories.full_name = %s
            )
            """,
            (repository,),
        )
        _run(
            connection,
            """
            DELETE FROM code_chunks
            WHERE repository_id IN (SELECT id FROM repositories WHERE full_name = %s)
            """,
            (repository,),
        )
        _run(connection, "DELETE FROM repositories WHERE full_name = %s", (repository,))
        _run(connection, "COMMIT")
        connection.close()
