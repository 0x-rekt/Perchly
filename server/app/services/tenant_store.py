"""Persistence for users, workspaces, memberships, and GitHub installations."""

import asyncio
import json
import re
from typing import Any

from app.services.review_queue import _execute, _run


def initialize_schema() -> None:
    def operation(connection) -> None:
        _run(connection, """
            CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY,
                github_id BIGINT NOT NULL UNIQUE,
                login TEXT NOT NULL,
                name TEXT NOT NULL,
                avatar_url TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        _run(connection, """
            CREATE TABLE IF NOT EXISTS workspaces (
                id BIGSERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                created_by_user_id BIGINT REFERENCES users(id),
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        _run(connection, """
            CREATE TABLE IF NOT EXISTS workspace_members (
                workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role TEXT NOT NULL DEFAULT 'member'
                    CHECK (role IN ('owner', 'admin', 'member')),
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (workspace_id, user_id)
            )
        """)
        _run(connection, """
            CREATE TABLE IF NOT EXISTS github_installations (
                id BIGSERIAL PRIMARY KEY,
                installation_id BIGINT NOT NULL UNIQUE,
                workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                account_login TEXT,
                account_type TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        _run(connection, """
            CREATE TABLE IF NOT EXISTS auth_sessions (
                id UUID PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TIMESTAMPTZ NOT NULL,
                revoked_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        _run(connection, """
            CREATE INDEX IF NOT EXISTS idx_workspace_members_user
            ON workspace_members(user_id)
        """)
        _run(connection, """
            CREATE INDEX IF NOT EXISTS idx_github_installations_workspace
            ON github_installations(workspace_id)
        """)
        _run(connection, "COMMIT")
    _execute(operation)


async def upsert_user_and_workspace(user: dict[str, Any]) -> dict[str, Any]:
    return await asyncio.to_thread(_upsert_user_and_workspace, user)


async def workspace_for_installation(installation_id: int) -> int | None:
    """Resolve the owning workspace for a GitHub App installation.

    The installation callback normally creates the explicit mapping. During
    the single-workspace migration, fall back to the only existing workspace
    so new webhook deliveries are not left unscoped.
    """
    return await asyncio.to_thread(_workspace_for_installation, installation_id)


async def link_installation(
    installation_id: int,
    *,
    workspace_id: int | None = None,
    account_login: str | None = None,
    account_type: str | None = None,
) -> int | None:
    """Attach a GitHub App installation to the single Perchly workspace."""
    return await asyncio.to_thread(
        _link_installation,
        installation_id,
        workspace_id,
        account_login,
        account_type,
    )


def _link_installation(
    installation_id: int,
    workspace_id: int | None,
    account_login: str | None,
    account_type: str | None,
) -> int | None:
    def operation(connection) -> int | None:
        initialize_schema_on_connection(connection)
        selected = workspace_id
        if selected is None:
            rows = _run(connection, "SELECT id FROM workspaces ORDER BY id DESC LIMIT 1")
            selected = int(rows[0][0]) if rows else None
        if selected is None:
            return None
        _run(connection, """
            INSERT INTO github_installations
                (installation_id, workspace_id, account_login, account_type)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (installation_id) DO UPDATE SET
                workspace_id = EXCLUDED.workspace_id,
                account_login = EXCLUDED.account_login,
                account_type = EXCLUDED.account_type,
                updated_at = CURRENT_TIMESTAMP
        """, (installation_id, selected, account_login, account_type))
        _run(connection, "COMMIT")
        return selected
    return _execute(operation)


def _workspace_for_installation(installation_id: int) -> int | None:
    def operation(connection) -> int | None:
        initialize_schema_on_connection(connection)
        rows = _run(connection, "SELECT workspace_id FROM github_installations WHERE installation_id = %s", (installation_id,))
        if rows:
            return int(rows[0][0])
        rows = _run(connection, "SELECT id FROM workspaces ORDER BY id DESC LIMIT 1")
        if not rows:
            return None
        workspace_id = int(rows[0][0])
        _run(connection, """
            INSERT INTO github_installations (installation_id, workspace_id)
            VALUES (%s, %s)
            ON CONFLICT (installation_id) DO NOTHING
        """, (installation_id, workspace_id))
        _run(connection, "COMMIT")
        return workspace_id
    return _execute(operation)


def _upsert_user_and_workspace(user: dict[str, Any]) -> dict[str, Any]:
    def operation(connection) -> dict[str, Any]:
        initialize_schema_on_connection(connection)
        row = _run(connection, """
            INSERT INTO users (github_id, login, name, avatar_url)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (github_id) DO UPDATE SET login = EXCLUDED.login,
                name = EXCLUDED.name, avatar_url = EXCLUDED.avatar_url,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id, github_id, login, name, avatar_url
        """, (user["github_id"], user["login"], user["name"], user.get("avatar_url")))[0]
        user_id = int(row[0])
        slug = _workspace_slug(str(user["login"]), user_id)
        workspace = _run(connection, """
            INSERT INTO workspaces (name, slug, created_by_user_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (slug) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
            RETURNING id, name, slug
        """, (f"{user['login']}'s workspace", slug, user_id))[0]
        workspace_id = int(workspace[0])
        _run(connection, """
            INSERT INTO workspace_members (workspace_id, user_id, role)
            VALUES (%s, %s, 'owner')
            ON CONFLICT (workspace_id, user_id) DO NOTHING
        """, (workspace_id, user_id))
        _run(connection, "COMMIT")
        return {**user, "user_id": user_id, "workspace_id": workspace_id}
    return _execute(operation)


def initialize_schema_on_connection(connection) -> None:
    _run(connection, """
        CREATE TABLE IF NOT EXISTS users (
            id BIGSERIAL PRIMARY KEY, github_id BIGINT NOT NULL UNIQUE,
            login TEXT NOT NULL, name TEXT NOT NULL, avatar_url TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    _run(connection, """
        CREATE TABLE IF NOT EXISTS workspaces (
            id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, slug TEXT NOT NULL UNIQUE,
            created_by_user_id BIGINT REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    _run(connection, """
        CREATE TABLE IF NOT EXISTS workspace_members (
            workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('owner', 'admin', 'member')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (workspace_id, user_id)
        )
    """)
    _run(connection, """
        CREATE TABLE IF NOT EXISTS github_installations (
            id BIGSERIAL PRIMARY KEY,
            installation_id BIGINT NOT NULL UNIQUE,
            workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            account_login TEXT,
            account_type TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)


def _workspace_slug(login: str, user_id: int) -> str:
    value = re.sub(r"[^a-z0-9-]+", "-", login.lower()).strip("-") or "workspace"
    return f"{value}-{user_id}"
