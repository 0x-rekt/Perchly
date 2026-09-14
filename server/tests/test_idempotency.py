from app.services.idempotency import IdempotencyStore


def test_store_rejects_duplicate_delivery_and_commit(tmp_path) -> None:
    store = IdempotencyStore(tmp_path / "perchly.sqlite3")
    event = {"repository": "acme/repo", "pr_number": 7, "head_sha": "abc123"}
    assert store.claim(delivery_id="delivery-1", **event)
    assert not store.claim(delivery_id="delivery-1", **event)
    assert not store.claim(delivery_id="delivery-2", **event)
    assert store.claim(delivery_id="delivery-3", repository="acme/repo", pr_number=7, head_sha="def456")


def test_released_failure_can_be_retried_by_a_new_delivery(tmp_path) -> None:
    store = IdempotencyStore(tmp_path / "perchly.sqlite3")
    event = {"repository": "acme/repo", "pr_number": 7, "head_sha": "abc123"}
    assert store.claim(delivery_id="delivery-1", **event)
    store.release_review(**event)
    assert store.claim(delivery_id="delivery-2", **event)
