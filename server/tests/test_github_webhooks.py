import hashlib
import hmac
import asyncio
import json

from starlette.requests import Request

import app.routers.github_webhooks as github_webhooks
from app.services.github_webhooks import valid_github_signature
from app.routers.github_webhooks import is_supported_pull_request_action


def test_valid_github_signature() -> None:
    body = b'{"action":"opened"}'
    secret = "test-secret"
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert valid_github_signature(raw_body=body, signature=signature, webhook_secret=secret)


def test_invalid_github_signature_is_rejected() -> None:
    assert not valid_github_signature(raw_body=b"body", signature="sha256=incorrect", webhook_secret="test-secret")


def test_only_required_pull_request_actions_are_supported() -> None:
    assert is_supported_pull_request_action("opened")
    assert is_supported_pull_request_action("synchronize")
    assert not is_supported_pull_request_action("closed")


def test_webhook_starts_temporal_workflow(monkeypatch) -> None:
    body = json.dumps({
        "action": "opened",
        "repository": {"full_name": "acme/repo"},
        "pull_request": {"number": 91, "head": {"sha": "sha-91"}},
        "installation": {"id": 42},
    }).encode()
    secret = "test-secret"
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    started = {}

    async def fake_start(input_data):
        started.update(vars(input_data))
        return "workflow-91"

    async def request_body():
        return body

    request = Request({"type": "http", "method": "POST", "path": "/webhooks/github", "headers": []})
    request.body = request_body
    monkeypatch.setattr(github_webhooks, "GITHUB_WEBHOOK_SECRET", secret)
    monkeypatch.setattr(github_webhooks, "valid_github_signature", lambda **kwargs: True)
    monkeypatch.setattr(github_webhooks, "start_review_workflow", fake_start)
    # Keep this unit test independent of the local idempotency database, which
    # may contain the same fixture delivery from an earlier test run.
    monkeypatch.setattr(github_webhooks.idempotency_store, "claim", lambda **kwargs: True)

    result = asyncio.run(github_webhooks.receive_github_events(
        request,
        x_github_event="pull_request",
        x_github_delivery="delivery-91",
        x_hub_signature_256=signature,
    ))

    assert result == {"status": "accepted", "delivery_id": "delivery-91"}
    assert started["repository"] == "acme/repo"
    assert started["head_sha"] == "sha-91"


def test_issue_comment_deletion_records_dismissed_outcome(monkeypatch) -> None:
    body = json.dumps({
        "action": "deleted",
        "repository": {"full_name": "acme/repo"},
        "issue": {"number": 91},
        "comment": {
            "body": "<!-- perchly-review:acme/repo:91:sha-91 -->\nreview"
        },
    }).encode()
    recorded = {}

    async def fake_record(**kwargs):
        recorded.update(kwargs)
        return 2

    async def request_body():
        return body

    request = Request({"type": "http", "method": "POST", "path": "/webhooks/github", "headers": []})
    request.body = request_body
    monkeypatch.setattr(github_webhooks, "GITHUB_WEBHOOK_SECRET", "test-secret")
    monkeypatch.setattr(github_webhooks, "valid_github_signature", lambda **kwargs: True)
    monkeypatch.setattr(github_webhooks.review_queue, "record_external_outcome", fake_record)

    result = asyncio.run(github_webhooks.receive_github_events(
        request,
        x_github_event="issue_comment",
        x_github_delivery="delivery-comment-91",
        x_hub_signature_256="ignored-in-test",
    ))

    assert result == {"status": "recorded", "outcome": "dismissed", "examples": "2"}
    assert recorded == {
        "repository": "acme/repo",
        "pr_number": 91,
        "head_sha": "sha-91",
        "final_outcome": "dismissed",
    }
