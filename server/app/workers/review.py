import logging

logger = logging.getLogger(__name__)


def enqueue_pr_review(
    *, delivery_id: str, repository: str, pr_number: int, head_sha: str, installation_id: int
) -> None:
    """Phase 0 review-job boundary; replace this with the actual review worker next."""
    logger.info(
        "Queued PR review delivery_id=%s repository=%s pr_number=%s head_sha=%s "
        "installation_id=%s",
        delivery_id,
        repository,
        pr_number,
        head_sha,
        installation_id,
    )
