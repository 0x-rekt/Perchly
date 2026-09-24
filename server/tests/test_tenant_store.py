from app.services import tenant_store


class _FakeConnection:
    pass


def test_installation_link_preserves_signed_workspace(monkeypatch) -> None:
    captured: dict[str, object] = {}
    connection = _FakeConnection()

    monkeypatch.setattr(tenant_store, "initialize_schema_on_connection", lambda _conn: None)
    monkeypatch.setattr(tenant_store, "_execute", lambda operation: operation(connection))

    def fake_run(_connection, query, params=()):
        if "INSERT INTO github_installations" in query:
            captured["params"] = params
            return [[params[1]]]
        if query == "COMMIT":
            return []
        raise AssertionError(f"unexpected query: {query}")

    monkeypatch.setattr(tenant_store, "_run", fake_run)

    result = tenant_store._link_installation(
        987, workspace_id=5, account_login="sample", account_type="User"
    )

    assert result == 5
    assert captured["params"] == (987, 5, "sample", "User")


def test_installation_without_signed_workspace_is_not_linked(monkeypatch) -> None:
    monkeypatch.setattr(
        tenant_store,
        "_execute",
        lambda operation: operation(_FakeConnection()),
    )
    monkeypatch.setattr(
        tenant_store,
        "initialize_schema_on_connection",
        lambda _connection: None,
    )
    monkeypatch.setattr(
        tenant_store,
        "_run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("must not create an unscoped installation")
        ),
    )

    assert tenant_store._link_installation(987, None, None, None) is None


def test_installation_lookup_uses_only_existing_active_mapping(monkeypatch) -> None:
    connection = _FakeConnection()
    captured: dict[str, object] = {}

    monkeypatch.setattr(tenant_store, "initialize_schema_on_connection", lambda _conn: None)
    monkeypatch.setattr(tenant_store, "_execute", lambda operation: operation(connection))

    def fake_run(_connection, query, params=()):
        captured["query"] = query
        captured["params"] = params
        return [[5]]

    monkeypatch.setattr(tenant_store, "_run", fake_run)

    assert tenant_store._workspace_for_installation(987) == 5
    assert "uninstalled_at IS NULL" in str(captured["query"])
    assert captured["params"] == (987,)


def test_installation_lookup_does_not_guess_workspace(monkeypatch) -> None:
    connection = _FakeConnection()
    monkeypatch.setattr(tenant_store, "initialize_schema_on_connection", lambda _conn: None)
    monkeypatch.setattr(tenant_store, "_execute", lambda operation: operation(connection))
    monkeypatch.setattr(tenant_store, "_run", lambda *_args, **_kwargs: [])

    assert tenant_store._workspace_for_installation(987) is None
