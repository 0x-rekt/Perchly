import hmac
from typing import Any, Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse

from app.services.auth import (
    AuthError, authorization_url, exchange_code, frontend_url, get_current_user,
    get_optional_user, installation_url, new_state, read_installation_state,
    read_session, session_token,
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
async def github_installation_callback(
    installation_id: int = Query(ge=1),
    setup_action: str = Query(default="install"),
    state: str | None = None,
    user: dict[str, Any] | None = Depends(get_optional_user),
) -> RedirectResponse:
    """Associate a GitHub App installation with the signed-in workspace."""
    if setup_action not in {"install", "update"}:
        raise HTTPException(status_code=400, detail="Unsupported GitHub installation action")
    workspace_id = read_installation_state(state)
    if workspace_id is None and user is not None:
        workspace_id = user.get("workspace_id")
    if not isinstance(workspace_id, int):
        raise HTTPException(status_code=409, detail="Session is not linked to a workspace")
    await link_installation(installation_id=installation_id, workspace_id=workspace_id)
    return RedirectResponse(f"{frontend_url()}/?installation=connected", status_code=status.HTTP_302_FOUND)


@router.get("/github/install")
async def github_install(user: dict[str, Any] = Depends(get_current_user)) -> RedirectResponse:
    workspace_id = user.get("workspace_id")
    if not isinstance(workspace_id, int):
        raise HTTPException(status_code=409, detail="Session is not linked to a workspace")
    try:
        return RedirectResponse(installation_url(workspace_id), status_code=status.HTTP_302_FOUND)
    except AuthError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    response.delete_cookie("perchly_session")
