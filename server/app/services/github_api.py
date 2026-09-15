import time
from dataclasses import dataclass
import posixpath
from pathlib import Path
import re
from typing import Any
from urllib.parse import quote

import httpx
import jwt

from app.core.config import GITHUB_API_URL


class GitHubApiError(RuntimeError):
    """Raised when GitHub rejects an API request needed for a review."""


@dataclass(frozen=True)
class RepositoryFile:
    path: str
    content: str


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

        async with httpx.AsyncClient(base_url=GITHUB_API_URL, timeout=30.0) as client:
            response = await client.request(
                method, path, headers=request_headers, json=json
            )

        if response.is_error:
            raise GitHubApiError(
                f"GitHub API {method} {path} failed with status {response.status_code}"
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

    async def create_pull_request_comment(
        self, *, repository: str, pr_number: int, body: str, installation_token: str
    ) -> None:
        await self._request(
            "POST",
            f"/repos/{repository}/issues/{pr_number}/comments",
            token=installation_token,
            json={"body": body},
        )


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
