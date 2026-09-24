import hmac
from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Response, status
from fastapi.responses import RedirectResponse

from app.services.auth import AuthError, authorization_url, exchange_code, frontend_url, new_state, read_session, session_token
from app.services.tenant_store import upsert_user_and_workspace

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


@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    response.delete_cookie("perchly_session")
