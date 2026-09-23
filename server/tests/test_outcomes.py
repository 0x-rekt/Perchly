import json

from app.services import review_queue
from app.services.outcome_retrieval import outcome_example_text


def test_findings_from_review_accepts_aggregated_payload() -> None:
    payload = {
        "review": {
            "findings": [{"category": "security", "message": "secret"}],
        }
    }

    assert review_queue._findings_from_review(payload["review"]) == [
        {"category": "security", "message": "secret"}
    ]


def test_insert_outcome_examples_writes_one_row_per_finding(
    monkeypatch,
) -> None:
    calls: list[tuple[str, tuple[object, ...]]] = []

    def fake_run(connection, query, parameters=()):
        calls.append((query, parameters))
        return []

    monkeypatch.setattr(review_queue, "_run", fake_run)
    review_queue._insert_outcome_examples(
        object(),
        repository="acme/repo",
        pr_number=7,
        head_sha="abc123",
        findings=[
            {
                "category": "security",
                "file": "src/config.py",
                "line_start": 4,
                "line_end": 4,
                "severity": "critical",
                "confidence": 0.99,
                "message": "Hardcoded secret",
            }
        ],
        final_outcome="rejected",
        reviewer="reviewer@example.com",
        source_queue_item_id=12,
    )

    assert len(calls) == 1
    params = calls[0][1]
    assert params[:3] == ("acme/repo", 7, "abc123")
    assert isinstance(params[3], str) and len(params[3]) == 64
    assert params[4] == "security"
    assert json.loads(params[5])["message"] == "Hardcoded secret"
    assert params[6:] == ("rejected", "reviewer@example.com", 12, None)


def test_outcome_example_text_contains_learning_label() -> None:
    text = outcome_example_text(
        {
            "category": "security",
            "severity": "critical",
            "file": "src/config.py",
            "line_start": 4,
            "line_end": 4,
            "message": "Hardcoded secret",
            "suggested_fix": "Use an environment variable",
        },
        "approved",
    )

    assert "category: security" in text
    assert "message: Hardcoded secret" in text
    assert "outcome: approved" in text


def test_review_queue_uses_simple_query_protocol_for_parameters() -> None:
    class FakeConnection:
        def __init__(self) -> None:
            self.query = ""
            self.params = None

        def run(self, query, **params):
            self.query = query
            self.params = params
            return []

    connection = FakeConnection()
    review_queue._run(
        connection,
        "SELECT * FROM review_queue WHERE status = %s AND repository = %s",
        ("pending", "acme/repo'; DROP TABLE review_queue; --"),
    )

    assert connection.params == {}
    assert "status = 'pending'" in connection.query
    assert "acme/repo''; DROP TABLE review_queue; --" in connection.query
