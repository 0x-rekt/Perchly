import asyncio
import pytest

import app.temporal.client as temporal_client_module
import app.temporal.workflows as workflows
from app.temporal.workflows import ReviewWorkflow, ReviewWorkflowInput


def _input() -> ReviewWorkflowInput:
    return ReviewWorkflowInput(
        delivery_id="delivery-1",
        repository="acme/repo",
        pr_number=7,
        head_sha="abc123",
        installation_id=42,
    )


def test_workflow_fans_out_all_specialists_and_posts(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def execute_activity(activity, argument, **kwargs):
        name = activity.__name__
        calls.append(name)
        if name == "fetch_review_context":
            return {
                "delivery_id": "delivery-1",
                "repository": "acme/repo",
                "pr_number": 7,
                "head_sha": "abc123",
                "installation_id": 42,
                "title": "Test",
                "description": "Description",
                "diff": "diff",
                "repository_files": [],
            }
        if name == "retrieve_repository_context":
            return {**argument, "contexts": {category: "context" for category in workflows._SPECIALIST_CATEGORIES}}
        if name == "run_specialist":
            return {"review": {"findings": []}, "category": argument["category"]}
        if name == "aggregate_review":
            return {"findings": [], "failures": argument["specialist_failures"]}
        if name == "post_review":
            return True
        if name == "release_review_claim":
            return None
        raise AssertionError(f"Unexpected activity: {name}")

    monkeypatch.setattr(workflows.workflow, "execute_activity", execute_activity)
    result = asyncio.run(ReviewWorkflow().run(_input()))

    assert result.findings_count == 0
    assert result.posted is True
    assert calls.count("run_specialist") == 4
    assert calls[-2:] == ["aggregate_review", "post_review"]


def test_workflow_keeps_partial_specialist_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def execute_activity(activity, argument, **kwargs):
        name = activity.__name__
        if name == "fetch_review_context":
            return {
                "delivery_id": "delivery-1", "repository": "acme/repo",
                "pr_number": 7, "head_sha": "abc123", "installation_id": 42,
                "title": "Test", "description": None, "diff": "diff",
                "repository_files": [],
            }
        if name == "retrieve_repository_context":
            return {**argument, "contexts": {}}
        if name == "run_specialist" and argument["category"] == "security":
            raise RuntimeError("Gemini unavailable")
        if name == "run_specialist":
            return {"review": {"findings": []}, "category": argument["category"]}
        if name == "aggregate_review":
            assert "security" in argument["specialist_failures"]
            return {"findings": [], "failures": argument["specialist_failures"]}
        if name == "post_review":
            return True
        if name == "release_review_claim":
            return None
        raise AssertionError(f"Unexpected activity: {name}")

    monkeypatch.setattr(workflows.workflow, "execute_activity", execute_activity)
    result = asyncio.run(ReviewWorkflow().run(_input()))

    assert result.posted is True


def test_activity_payload_annotations_are_temporal_decodable() -> None:
    from app.temporal import activities

    for name in (
        "fetch_review_context", "retrieve_repository_context", "run_specialist",
        "aggregate_review", "post_review", "release_review_claim",
    ):
        annotation = getattr(activities, name).__annotations__
        assert all("object" not in str(value) for value in annotation.values())


def test_start_review_workflow_uses_deterministic_id(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeHandle:
        id = "perchly-review-acme/repo-7-abc123"

    class FakeClient:
        async def start_workflow(self, workflow, input_data, **kwargs):
            assert workflow == workflows.ReviewWorkflow.run
            assert input_data == _input()
            assert kwargs["id"] == "perchly-review-acme/repo-7-abc123"
            assert kwargs["task_queue"] == "perchly-reviews"
            assert kwargs["id_reuse_policy"].name == "REJECT_DUPLICATE"
            return FakeHandle()

    async def fake_temporal_client():
        return FakeClient()

    monkeypatch.setattr(temporal_client_module, "temporal_client", fake_temporal_client)
    workflow_id = asyncio.run(temporal_client_module.start_review_workflow(_input()))

    assert workflow_id == "perchly-review-acme/repo-7-abc123"
