import asyncio
import pytest

import app.temporal.client as temporal_client_module
import app.temporal.workflows as workflows
from app.temporal.workflows import ReviewDecisionInput, ReviewWorkflow, ReviewWorkflowInput


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
        if name == "route_aggregated_review":
            return {"mode": "auto_post", "reason": "all_findings_meet_policy", "queue_item_id": None}
        if name == "post_review":
            return True
        if name == "persist_automatic_decision":
            return 1
        if name == "release_review_claim":
            return None
        raise AssertionError(f"Unexpected activity: {name}")

    monkeypatch.setattr(workflows.workflow, "execute_activity", execute_activity)
    result = asyncio.run(ReviewWorkflow().run(_input()))

    assert result.findings_count == 0
    assert result.posted is True
    assert calls.count("run_specialist") == 4
    assert calls[-4:] == [
        "aggregate_review",
        "route_aggregated_review",
        "post_review",
        "persist_automatic_decision",
    ]


def test_workflow_keeps_partial_specialist_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    workflow_instance: ReviewWorkflow

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
        if name == "route_aggregated_review":
            workflow_instance.decision = ReviewDecisionInput(
                decision="approve",
                reviewer="reviewer@example.com",
                comment="Looks good",
            )
            return {"mode": "needs_approval", "reason": "specialist_failure", "queue_item_id": 9}
        if name == "persist_reviewer_decision":
            return 1
        if name == "post_review":
            return True
        if name == "release_review_claim":
            return None
        raise AssertionError(f"Unexpected activity: {name}")

    monkeypatch.setattr(workflows.workflow, "execute_activity", execute_activity)
    async def immediate_wait_condition(condition):
        assert condition()

    monkeypatch.setattr(workflows.workflow, "wait_condition", immediate_wait_condition)
    workflow_instance = ReviewWorkflow()
    result = asyncio.run(workflow_instance.run(_input()))

    assert result.posted is True
    assert result.route == "needs_approval"


def test_activity_payload_annotations_are_temporal_decodable() -> None:
    from app.temporal import activities

    for name in (
        "fetch_review_context", "retrieve_repository_context", "run_specialist",
        "aggregate_review", "route_aggregated_review", "post_review",
        "persist_automatic_decision", "persist_reviewer_decision",
        "validate_edited_review", "release_review_claim",
    ):
        annotation = getattr(activities, name).__annotations__
        assert all("object" not in str(value) for value in annotation.values())


def test_review_decision_payload_annotations_are_temporal_decodable() -> None:
    assert all("object" not in str(value) for value in ReviewDecisionInput.__annotations__.values())


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


def test_temporal_client_helpers_lookup_and_signal_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, object]] = []

    class FakeHandle:
        async def signal(self, signal, payload):
            calls.append((signal.__name__, payload))

        async def query(self, query):
            calls.append((query.__name__, None))
            return {"state": "awaiting_approval", "decision": None}

    class FakeClient:
        def get_workflow_handle(self, workflow_id):
            assert workflow_id == "perchly-review-acme/repo-7-abc123"
            return FakeHandle()

    async def fake_temporal_client():
        return FakeClient()

    monkeypatch.setattr(temporal_client_module, "temporal_client", fake_temporal_client)
    asyncio.run(
        temporal_client_module.send_approval_signal(
            _input(), reviewer="approver@example.com", comment="Approved"
        )
    )
    asyncio.run(
        temporal_client_module.send_rejection_signal(
            _input(), reviewer="rejector@example.com"
        )
    )
    asyncio.run(
        temporal_client_module.send_edited_review_signal(
            _input(),
            reviewer="editor@example.com",
            edited_review={"findings": [], "failures": {}},
        )
    )
    status = asyncio.run(temporal_client_module.query_review_status(_input()))

    assert [name for name, _ in calls] == [
        "approve_review",
        "reject_review",
        "edit_review",
        "status",
    ]
    assert calls[0][1].decision == "approve"
    assert calls[1][1].decision == "reject"
    assert calls[2][1].decision == "edit"
    assert status["state"] == "awaiting_approval"
