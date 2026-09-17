import hashlib
import hmac

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
