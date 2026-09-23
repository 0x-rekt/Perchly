import time
import base64
from dataclasses import dataclass
import posixpath
from pathlib import Path
import re
from typing import Any
from urllib.parse import quote

import httpx
import jwt

from app.core.config import GITHUB_API_URL
from app.services.telemetry import otel_span


class GitHubApiError(RuntimeError):
    """Raised when GitHub rejects an API request needed for a review."""

    def __init__(self, message: str, *, status_code: int | None = None, response_text: str = "") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


GENERATED_FIX_PR_MARKER = "<!-- perchly-generated-fix-pr -->"


@dataclass(frozen=True)
class RepositoryFile:
    path: str
    content: str


@dataclass(frozen=True)
class RepositoryFileVersion:
    path: str
    content: str
    sha: str


_RELATIVE_IMPORT = re.compile(
    r"(?:from\s*|import\s*|require\(\s*)[\"'](\.?\.?/[^\"']+)[\"']"
)


class GitHubAppClient:
    """Small GitHub App client for the Phase 0 review workflow."""

    def __init__(self, *, app_id: str, private_key_path: Path) -> None:
        self._app_id = app_id
        self._private_key_path = private_key_path

    def _app_jwt(self) -> str:
        now = int(time.time())
        private_key = self._private_key_path.read_bytes()
        return jwt.encode(
            {"iat": now - 60, "exp": now + 540, "iss": self._app_id},
            private_key,
            algorithm="RS256",
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        token: str,
        headers: dict[str, str] | None = None,
        json: dict[str, object] | None = None,
    ) -> httpx.Response:
        request_headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2026-03-10",
        }
        if headers:
            request_headers.update(headers)

        with otel_span(
            "perchly.tool.github_api",
            attributes={
                "perchly.span_type": "tool_call",
                "http.request.method": method,
                "http.request.path": path.split("?", 1)[0],
                "server.address": GITHUB_API_URL,
            },
        ) as span:
            async with httpx.AsyncClient(base_url=GITHUB_API_URL, timeout=30.0) as client:
                response = await client.request(
                    method, path, headers=request_headers, json=json
                )
            span.set_attribute("http.response.status_code", response.status_code)

            if response.is_error:
                raise GitHubApiError(
                    f"GitHub API {method} {path} failed with status {response.status_code}",
                    status_code=response.status_code,
                    response_text=response.text[:1000],
                )
            return response

    async def installation_token(self, installation_id: int) -> str:
        response = await self._request(
            "POST",
            f"/app/installations/{installation_id}/access_tokens",
            token=self._app_jwt(),
        )
        token = response.json().get("token")
        if not isinstance(token, str):
            raise GitHubApiError("GitHub installation-token response did not contain a token")
        return token

    async def pull_request_diff(
        self, *, repository: str, pr_number: int, installation_token: str
    ) -> str:
        response = await self._request(
            "GET",
            f"/repos/{repository}/pulls/{pr_number}",
            token=installation_token,
            headers={"Accept": "application/vnd.github.v3.diff"},
        )
        return response.text

    async def pull_request_details(
        self, *, repository: str, pr_number: int, installation_token: str
    ) -> tuple[str, str | None]:
        response = await self._request(
            "GET",
            f"/repos/{repository}/pulls/{pr_number}",
            token=installation_token,
        )
        payload: dict[str, Any] = response.json()
        title = payload.get("title")
        body = payload.get("body")
        if not isinstance(title, str):
            raise GitHubApiError("GitHub pull-request response did not contain a title")
        return title, body if isinstance(body, str) else None

    async def pull_request_repository_context(
        self,
        *,
        repository: str,
        pr_number: int,
        head_sha: str,
        installation_token: str,
    ) -> list[RepositoryFile]:
        """Fetch full contents for changed text files at the PR head revision."""
        changed_files: list[object] = []
        page = 1
        while True:
            response = await self._request(
                "GET",
                f"/repos/{repository}/pulls/{pr_number}/files?per_page=100&page={page}",
                token=installation_token,
            )
            payload = response.json()
            if not isinstance(payload, list):
                raise GitHubApiError("GitHub changed-files response was not a list")
            changed_files.extend(payload)
            if len(payload) < 100:
                break
            page += 1

        files: list[RepositoryFile] = []
        known_paths: set[str] = set()
        for item in changed_files:
            if not isinstance(item, dict):
                continue
            path = item.get("filename")
            if not isinstance(path, str) or item.get("status") == "removed":
                continue
            try:
                content = await self.repository_file_content(
                    repository=repository,
                    path=path,
                    revision=head_sha,
                    installation_token=installation_token,
                )
            except GitHubApiError:
                # Binary/generated files may not have text content; the diff remains available.
                continue
            if content is not None:
                files.append(RepositoryFile(path=path, content=content))
                known_paths.add(path)

        related_paths = {
            candidate
            for repository_file in files
            for reference in _RELATIVE_IMPORT.findall(repository_file.content)
            for candidate in _repository_import_candidates(repository_file.path, reference)
            if candidate not in known_paths
        }
        for path in sorted(related_paths)[:20]:
            try:
                content = await self.repository_file_content(
                    repository=repository,
                    path=path,
                    revision=head_sha,
                    installation_token=installation_token,
                )
            except GitHubApiError:
                continue
            if content is not None:
                files.append(RepositoryFile(path=path, content=content))
        return files

    async def repository_file_content(
        self,
        *,
        repository: str,
        path: str,
        revision: str,
        installation_token: str,
    ) -> str | None:
        response = await self._request(
            "GET",
            f"/repos/{repository}/contents/{quote(path, safe='/')}?ref={quote(revision)}",
            token=installation_token,
            headers={"Accept": "application/vnd.github.raw+json"},
        )
        return response.text or None

    async def repository_file_version(
        self, *, repository: str, path: str, revision: str, installation_token: str
    ) -> RepositoryFileVersion:
        response = await self._request(
            "GET",
            f"/repos/{repository}/contents/{quote(path, safe='/')}?ref={quote(revision)}",
            token=installation_token,
        )
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("type") != "file":
            raise GitHubApiError(f"GitHub path is not a file: {path}")
        encoded = payload.get("content")
        sha = payload.get("sha")
        if not isinstance(encoded, str) or not isinstance(sha, str):
            raise GitHubApiError(f"GitHub file response is missing content or sha: {path}")
        try:
            content = base64.b64decode(encoded.replace("\n", "")).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as error:
            raise GitHubApiError(f"GitHub file is not UTF-8 text: {path}") from error
        return RepositoryFileVersion(path=path, content=content, sha=sha)

    async def pull_request_base_branch(
        self, *, repository: str, pr_number: int, installation_token: str
    ) -> str:
        response = await self._request(
            "GET", f"/repos/{repository}/pulls/{pr_number}", token=installation_token
        )
        payload = response.json()
        base = payload.get("base") if isinstance(payload, dict) else None
        branch = base.get("ref") if isinstance(base, dict) else None
        if not isinstance(branch, str) or not branch:
            raise GitHubApiError("GitHub pull-request response did not contain a base branch")
        return branch

    async def create_branch(
        self, *, repository: str, branch: str, from_sha: str, installation_token: str
    ) -> None:
        await self._request(
            "POST",
            f"/repos/{repository}/git/refs",
            token=installation_token,
            json={"ref": f"refs/heads/{branch}", "sha": from_sha},
        )

    async def ensure_branch(
        self, *, repository: str, branch: str, from_sha: str, installation_token: str
    ) -> None:
        try:
            await self._request(
                "GET", f"/repos/{repository}/git/ref/heads/{quote(branch, safe='/')}",
                token=installation_token,
            )
        except GitHubApiError as error:
            if "status 404" not in str(error):
                raise
            await self.create_branch(
                repository=repository, branch=branch, from_sha=from_sha,
                installation_token=installation_token,
            )

    async def find_open_pull_request(
        self, *, repository: str, head: str, installation_token: str
    ) -> str | None:
        owner = repository.split("/", 1)[0]
        response = await self._request(
            "GET",
            f"/repos/{repository}/pulls?state=open&head={quote(owner + ':' + head, safe=':')}",
            token=installation_token,
        )
        payload = response.json()
        if not isinstance(payload, list):
            raise GitHubApiError("GitHub pull-request response was not a list")
        for item in payload:
            if isinstance(item, dict) and isinstance(item.get("html_url"), str):
                return item["html_url"]
        return None

    async def update_repository_file(
        self,
        *,
        repository: str,
        path: str,
        branch: str,
        content: str,
        file_sha: str,
        message: str,
        installation_token: str,
    ) -> None:
        await self._request(
            "PUT",
            f"/repos/{repository}/contents/{quote(path, safe='/')}",
            token=installation_token,
            json={
                "message": message,
                "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
                "branch": branch,
                "sha": file_sha,
            },
        )

    async def create_pull_request(
        self,
        *,
        repository: str,
        head: str,
        base: str,
        title: str,
        body: str,
        installation_token: str,
    ) -> str:
        response = await self._request(
            "POST",
            f"/repos/{repository}/pulls",
            token=installation_token,
            json={"title": title, "body": body, "head": head, "base": base},
        )
        payload = response.json()
        url = payload.get("html_url") if isinstance(payload, dict) else None
        if not isinstance(url, str):
            raise GitHubApiError("GitHub pull-request response did not contain html_url")
        return url

    async def create_pull_request_comment(
        self, *, repository: str, pr_number: int, body: str, installation_token: str
    ) -> None:
        await self._request(
            "POST",
            f"/repos/{repository}/issues/{pr_number}/comments",
            token=installation_token,
            json={"body": body},
        )

    async def create_idempotent_pull_request_comment(
        self,
        *,
        repository: str,
        pr_number: int,
        body: str,
        marker: str,
        installation_token: str,
    ) -> bool:
        """Create a comment only when no existing comment contains the marker."""
        page = 1
        while True:
            response = await self._request(
                "GET",
                f"/repos/{repository}/issues/{pr_number}/comments?per_page=100&page={page}",
                token=installation_token,
            )
            payload = response.json()
            if not isinstance(payload, list):
                raise GitHubApiError("GitHub issue-comments response was not a list")
            if any(
                isinstance(comment, dict)
                and marker in (comment.get("body") or "")
                for comment in payload
            ):
                return False
            if len(payload) < 100:
                break
            page += 1

        await self.create_pull_request_comment(
            repository=repository,
            pr_number=pr_number,
            body=f"{marker}\n{body}",
            installation_token=installation_token,
        )
        return True


def review_comment_marker(*, repository: str, pr_number: int, head_sha: str) -> str:
    """Return the stable marker used to make one review idempotent."""
    return f"<!-- perchly-review:{repository}:{pr_number}:{head_sha} -->"


def _repository_import_candidates(source_path: str, reference: str) -> list[str]:
    base = posixpath.normpath(posixpath.join(posixpath.dirname(source_path), reference))
    candidates = [base]
    if not posixpath.splitext(base)[1]:
        candidates.extend(
            f"{base}{extension}"
            for extension in (".ts", ".tsx", ".js", ".jsx", ".py")
        )
        candidates.extend(
            f"{base}/index{extension}"
            for extension in (".ts", ".tsx", ".js", ".jsx", ".py")
        )
    return candidates
