from app.services import auth


def test_installation_state_is_signed_and_scoped(monkeypatch) -> None:
    monkeypatch.setattr(auth, "session_secret", lambda: "s" * 40)

    token = auth.installation_state_token(
        {"github_id": 123, "workspace_id": 7, "login": "maintainer"}
    )
    payload = auth.read_installation_state(token)

    assert payload is not None
    assert payload["purpose"] == "github-installation"
    assert payload["github_id"] == 123
    assert payload["workspace_id"] == 7
    assert isinstance(payload["nonce"], str)


def test_installation_state_rejects_tampered_token(monkeypatch) -> None:
    monkeypatch.setattr(auth, "session_secret", lambda: "s" * 40)

    token = auth.installation_state_token({"github_id": 123, "workspace_id": 7})
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")

    assert auth.read_installation_state(tampered) is None
    assert auth.read_installation_state(None) is None
