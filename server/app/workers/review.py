import logging

from app.core.config import github_app_credentials
from app.services.github_api import GitHubAppClient

logger = logging.getLogger(__name__)


async def review_pull_request(
    *, delivery_id: str, repository: str, pr_number: int, head_sha: str, installation_id: int
) -> None:
    """Fetch authenticated PR context; LLM analysis and publishing follow in the next slice."""
    logger.info(
        "Starting PR review delivery_id=%s repository=%s pr_number=%s head_sha=%s",
        delivery_id,
        repository,
        pr_number,
        head_sha,
    )

    try:
        app_id, private_key_path = github_app_credentials()
        github = GitHubAppClient(app_id=app_id, private_key_path=private_key_path)
        installation_token = await github.installation_token(installation_id)
        diff = await github.pull_request_diff(
            repository=repository,
            pr_number=pr_number,
            installation_token=installation_token,
        )
    except Exception:
        logger.exception(
            "PR review failed delivery_id=%s repository=%s pr_number=%s",
            delivery_id,
            repository,
            pr_number,
        )
        return

    logger.info(
        "Fetched PR diff delivery_id=%s repository=%s pr_number=%s head_sha=%s "
        "diff_characters=%s",
        delivery_id,
        repository,
        pr_number,
        head_sha,
        len(diff),
    )
