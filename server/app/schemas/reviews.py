from typing import Any

from pydantic import BaseModel, Field

from app.schemas.findings import Finding


class ReviewDecisionRequest(BaseModel):
    reviewer: str = Field(min_length=1)
    comment: str | None = None


class EditedReviewPayload(BaseModel):
    findings: list[Finding] = Field(default_factory=list)
    failures: dict[str, str] = Field(default_factory=dict)


class EditReviewRequest(ReviewDecisionRequest):
    edited_review: EditedReviewPayload


class FixPullRequestRequest(BaseModel):
    reviewer: str = Field(min_length=1)
