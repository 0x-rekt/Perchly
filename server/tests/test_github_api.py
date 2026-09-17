from pathlib import Path
from types import SimpleNamespace

import asyncio
from urllib.parse import parse_qs, urlparse

from app.services.github_api import GitHubAppClient


def test_pull_request_repository_context_paginates_changed_files() -> None:
    first_page = [{"filename": f"src/file_{index}.py", "status": "modified"} for index in range(100)]
    second_page = [{"filename": "src/file_100.py", "status": "modified"}]

    class FakeGitHubClient(GitHubAppClient):
        def __init__(self) -> None:
            super().__init__(app_id="test", private_key_path=Path("missing.pem"))
            self.paths: list[str] = []

        async def _request(self, method: str, path: str, *, token: str, headers=None, json=None):
            self.paths.append(path)
            page = parse_qs(urlparse(path).query)["page"][0]
            payload = first_page if page == "1" else second_page
            return SimpleNamespace(json=lambda: payload)

        async def repository_file_content(
            self, *, repository: str, path: str, revision: str, installation_token: str
        ) -> str:
            return f"content for {path}"

    client = FakeGitHubClient()
    files = asyncio.run(
        client.pull_request_repository_context(
            repository="acme/repo",
            pr_number=1,
            head_sha="head-sha",
            installation_token="token",
        )
    )

    assert client.paths == [
        "/repos/acme/repo/pulls/1/files?per_page=100&page=1",
        "/repos/acme/repo/pulls/1/files?per_page=100&page=2",
    ]
    assert len(files) == 101
    assert files[-1].path == "src/file_100.py"


def test_idempotent_comment_skips_existing_marker() -> None:
    class FakeGitHubClient(GitHubAppClient):
        def __init__(self) -> None:
            super().__init__(app_id="test", private_key_path=Path("missing.pem"))
            self.posts = 0

        async def _request(self, method: str, path: str, *, token: str, headers=None, json=None):
            if method == "GET":
                return SimpleNamespace(json=lambda: [{"body": "<!-- marker -->"}])
            self.posts += 1
            return SimpleNamespace(json=lambda: {})

    client = FakeGitHubClient()
    posted = asyncio.run(
        client.create_idempotent_pull_request_comment(
            repository="acme/repo",
            pr_number=1,
            body="review",
            marker="<!-- marker -->",
            installation_token="token",
        )
    )

    assert not posted
    assert client.posts == 0