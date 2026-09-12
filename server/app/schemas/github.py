from pydantic import BaseModel


class RepositoryPayload(BaseModel):
    full_name: str


class PullRequestHeadPayload(BaseModel):
    sha: str


class PullRequestPayload(BaseModel):
    number: int
    head: PullRequestHeadPayload


class InstallationPayload(BaseModel):
    id: int


class PullRequestWebhookPayload(BaseModel):
    action: str
    repository: RepositoryPayload
    pull_request: PullRequestPayload
    installation: InstallationPayload
