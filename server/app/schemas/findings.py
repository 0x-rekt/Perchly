import hashlib
import json
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, Field

FindingCategory = Literal["security", "quality", "test_coverage", "docs"]
FindingSeverity = Literal["info", "warning", "critical"]


class Finding(BaseModel):
    # Assigned after aggregation, once repository and commit context are known.
    finding_id: str | None = Field(default=None, min_length=1)
    category: FindingCategory
    file: str = Field(min_length=1)
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    severity: FindingSeverity
    confidence: float = Field(ge=0, le=1)
    message: str = Field(min_length=1)
    suggested_fix: str | None = None


class ReviewResult(BaseModel):
    findings: list[Finding] = Field(default_factory=list)


def stable_finding_id(
    *,
    repository: str,
    pr_number: int,
    head_sha: str,
    finding: Finding | Mapping[str, object],
) -> str:
    """Return a deterministic identity for a finding in one reviewed commit."""
    values = finding.model_dump() if isinstance(finding, Finding) else dict(finding)
    identity = {
        "repository": repository,
        "pr_number": pr_number,
        "head_sha": head_sha,
        "category": values.get("category"),
        "file": values.get("file"),
        "line_start": values.get("line_start"),
        "line_end": values.get("line_end"),
        "message": values.get("message"),
    }
    payload = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def assign_finding_ids(
    findings: list[Finding] | tuple[Finding, ...],
    *,
    repository: str,
    pr_number: int,
    head_sha: str,
) -> list[Finding]:
    """Attach stable IDs after a review has its repository/commit context."""
    return [
        finding.model_copy(
            update={
                "finding_id": stable_finding_id(
                    repository=repository,
                    pr_number=pr_number,
                    head_sha=head_sha,
                    finding=finding,
                )
            }
        )
        for finding in findings
    ]
