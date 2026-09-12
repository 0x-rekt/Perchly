import hashlib
import hmac


def valid_github_signature(
    *, raw_body: bytes, signature: str | None, webhook_secret: str | None
) -> bool:
    """Verify GitHub's sha256 HMAC signature against the unmodified request body."""
    if not webhook_secret or not signature:
        return False

    expected_signature = "sha256=" + hmac.new(
        webhook_secret.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_signature, signature)
