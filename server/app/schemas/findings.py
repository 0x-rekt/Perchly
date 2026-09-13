from typing import Literal

from pydantic import BaseModel, Field

FindingCategory = Literal["security", "quality", "test_coverage", "docs"]
FindingSeverity = Literal["info", "warning", "critical"]


class Finding(BaseModel):
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
