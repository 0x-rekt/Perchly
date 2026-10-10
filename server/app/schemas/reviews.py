from typing import Any

from pydantic import BaseModel, Field

from app.schemas.findings import Finding


class ReviewDecisionRequest(BaseModel):
    reviewer: str | None = Field(default=None, min_length=1)
    comment: str | None = None


class EditedReviewPayload(BaseModel):
    findings: list[Finding] = Field(default_factory=list)
    failures: dict[str, str] = Field(default_factory=dict)


class EditReviewRequest(ReviewDecisionRequest):
    edited_review: EditedReviewPayload


class FixPullRequestRequest(BaseModel):
    reviewer: str | None = Field(default=None, min_length=1)


class RepositoryIndexRequest(BaseModel):
    repository: str = Field(min_length=3, pattern=r"^[^/\s]+/[^/\s]+$")
    installation_id: int = Field(gt=0)
    revision: str | None = Field(default=None, min_length=1)
