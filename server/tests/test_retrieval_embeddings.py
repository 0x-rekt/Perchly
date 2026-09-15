from types import SimpleNamespace

from app.services import retrieval


class FakeEmbeddingClient:
    def __init__(self) -> None:
        self.inputs: list[str] = []
        self.models = self

    def embed_content(self, *, model: str, contents: str, config) -> SimpleNamespace:
        self.inputs.append(contents)
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=[0.1] * retrieval.EMBEDDING_DIMENSIONS)]
        )


def test_embed_requests_one_vector_per_chunk(monkeypatch) -> None:
    client = FakeEmbeddingClient()
    monkeypatch.setattr(retrieval, "GEMINI_EMBEDDING_MODEL", "test-embedding-model")

    embeddings = retrieval._embed(client, ["first chunk", "second chunk"])

    assert client.inputs == ["first chunk", "second chunk"]
    assert len(embeddings) == 2
    assert all(len(embedding) == retrieval.EMBEDDING_DIMENSIONS for embedding in embeddings)