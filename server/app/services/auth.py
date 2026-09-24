"""GitHub user authorization and signed dashboard sessions."""

import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import Cookie, HTTPException, status

from app.core.config import (
    GITHUB_APP_SLUG,
    GITHUB_OAUTH_CLIENT_ID,
    GITHUB_OAUTH_CLIENT_SECRET,
    GITHUB_OAUTH_REDIRECT_URI,
    WEB_APP_URL,
    session_secret,
)


class AuthError(RuntimeError):
    pass


def get_current_user(perchly_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    """FastAPI dependency used by all authenticated dashboard APIs."""
    user = read_session(perchly_session)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_optional_user(perchly_session: str | None = Cookie(default=None)) -> dict[str, Any] | None:
    return read_session(perchly_session)


def authorization_url(state: str) -> str:
    if not GITHUB_OAUTH_CLIENT_ID:
        raise AuthError("GITHUB_OAUTH_CLIENT_ID must be configured")
    return "https://github.com/login/oauth/authorize?" + urlencode({
        "client_id": GITHUB_OAUTH_CLIENT_ID,
        "redirect_uri": GITHUB_OAUTH_REDIRECT_URI,
        "state": state,
        "scope": "read:user user:email",
    })


def new_state() -> str:
    return secrets.token_urlsafe(32)


async def exchange_code(code: str) -> dict[str, Any]:
    if not GITHUB_OAUTH_CLIENT_ID or not GITHUB_OAUTH_CLIENT_SECRET:
        raise AuthError("GitHub OAuth credentials are not configured")
    async with httpx.AsyncClient(timeout=15) as client:
        token_response = await client.post(
            "https://github.com/login/oauth/access_token",
            json={
                "client_id": GITHUB_OAUTH_CLIENT_ID,
                "client_secret": GITHUB_OAUTH_CLIENT_SECRET,
                "code": code,
                "redirect_uri": GITHUB_OAUTH_REDIRECT_URI,
            },
            headers={"Accept": "application/json"},
        )
        token_response.raise_for_status()
        token = token_response.json().get("access_token")
        if not isinstance(token, str):
            raise AuthError("GitHub did not return an access token")
        user_response = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        )
        user_response.raise_for_status()
        user = user_response.json()
    if not isinstance(user, dict) or not isinstance(user.get("id"), int) or not isinstance(user.get("login"), str):
        raise AuthError("GitHub returned an invalid user profile")
    return {
        "github_id": user["id"],
        "login": user["login"],
        "name": user.get("name") if isinstance(user.get("name"), str) else user["login"],
        "avatar_url": user.get("avatar_url") if isinstance(user.get("avatar_url"), str) else None,
    }


def session_token(user: dict[str, Any]) -> str:
    now = int(time.time())
    return jwt.encode(
        {**user, "iat": now, "exp": now + 7 * 24 * 60 * 60},
        session_secret(),
        algorithm="HS256",
    )


def read_session(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    try:
        payload = jwt.decode(token, session_secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    return payload if isinstance(payload.get("github_id"), int) else None


def frontend_url() -> str:
    return WEB_APP_URL.rstrip("/")


def installation_url(workspace_id: int) -> str:
    if not GITHUB_APP_SLUG:
        raise AuthError("GITHUB_APP_SLUG must be configured")
    state = jwt.encode(
        {"purpose": "github-installation", "workspace_id": workspace_id, "exp": int(time.time()) + 600},
        session_secret(), algorithm="HS256",
    )
    return f"https://github.com/apps/{GITHUB_APP_SLUG}/installations/new?" + urlencode({"state": state})


def read_installation_state(value: str | None) -> int | None:
    if not value:
        return None
    try:
        payload = jwt.decode(value, session_secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    workspace_id = payload.get("workspace_id")
    return workspace_id if payload.get("purpose") == "github-installation" and isinstance(workspace_id, int) else None
