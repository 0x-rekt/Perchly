import hmac
from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Response, status
from fastapi.responses import RedirectResponse
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.core.config import GITHUB_APP_INSTALL_URL
from app.services.auth import (
    AuthError,
    authorization_url,
    exchange_code,
    frontend_url,
    installation_state_token,
    new_state,
    read_installation_state,
    read_session,
    session_token,
)
from app.services.tenant_store import link_installation, upsert_user_and_workspace

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/github")
async def github_login() -> RedirectResponse:
    state = new_state()
    response = RedirectResponse(authorization_url(state), status_code=status.HTTP_302_FOUND)
    response.set_cookie("perchly_oauth_state", state, httponly=True, secure=False, samesite="lax", max_age=600)
    return response


@router.get("/github/callback")
async def github_callback(code: str, state: str, perchly_oauth_state: Annotated[str | None, Cookie()] = None) -> RedirectResponse:
    if not perchly_oauth_state or not state or not hmac.compare_digest(state, perchly_oauth_state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    try:
        user = await exchange_code(code)
        user = await upsert_user_and_workspace(user)
        token = session_token(user)
    except AuthError as error:
        raise HTTPException(status_code=502, detail="GitHub authentication failed") from error
    response = RedirectResponse(frontend_url(), status_code=status.HTTP_302_FOUND)
    response.delete_cookie("perchly_oauth_state")
    response.set_cookie("perchly_session", token, httponly=True, secure=False, samesite="lax", max_age=7 * 24 * 60 * 60)
    return response


@router.get("/me")
async def current_user(perchly_session: Annotated[str | None, Cookie()] = None) -> dict[str, object]:
    user = read_session(perchly_session)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {key: value for key, value in user.items() if key not in {"iat", "exp"}}


@router.get("/github/installation")
async def github_installation(
    installation_id: int,
    setup_action: str = "install",
    account_login: str | None = None,
    account_type: str | None = None,
    state: str | None = None,
) -> RedirectResponse:
    """Map this installation using signed state from the initiating workspace."""
    install_state = read_installation_state(state)
    workspace_id = install_state.get("workspace_id") if install_state else None
    linked_workspace = await link_installation(
        installation_id,
        workspace_id=workspace_id,
        account_login=account_login,
        account_type=account_type,
    )
    params = {"installation": "connected" if linked_workspace is not None else "error", "setup_action": setup_action}
    return RedirectResponse(f"{frontend_url()}?{urlencode(params)}", status_code=status.HTTP_302_FOUND)


@router.get("/github/install")
async def begin_github_installation(
    perchly_session: Annotated[str | None, Cookie()] = None,
) -> RedirectResponse:
    """Start GitHub App installation with signed, expiring workspace context."""
    user = read_session(perchly_session)
    if user is None:
        return RedirectResponse("/auth/github", status_code=status.HTTP_302_FOUND)
    try:
        state = installation_state_token(user)
    except AuthError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    parsed = urlparse(GITHUB_APP_INSTALL_URL)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["state"] = state
    target = urlunparse(parsed._replace(query=urlencode(query)))
    return RedirectResponse(target, status_code=status.HTTP_302_FOUND)


@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    response.delete_cookie("perchly_session")
