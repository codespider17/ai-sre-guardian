from uuid import uuid4

import pytest

from app.schemas_agent import AgentRun, AgentState
from app.services.agent_state import (
    ALLOWED_TRANSITIONS,
    InvalidAgentTransitionError,
    TerminalAgentRunError,
    create_agent_run,
    execute_nominal_workflow,
    transition_agent,
)


def new_run() -> AgentRun:
    return create_agent_run(uuid4())


def test_new_agent_run_starts_in_created_state() -> None:
    run = new_run()
    assert run.state == AgentState.CREATED
    assert run.steps == []
    assert run.failure_reason is None


def test_nominal_workflow_reaches_completed() -> None:
    run = execute_nominal_workflow(new_run())
    assert run.state == AgentState.COMPLETED
    assert len(run.steps) == 6


def test_nominal_history_is_ordered_and_contiguous() -> None:
    run = execute_nominal_workflow(new_run())
    assert [step.sequence for step in run.steps] == list(range(1, 7))
    assert all(
        current.to_state == following.from_state
        for current, following in zip(run.steps, run.steps[1:], strict=False)
    )


def test_state_machine_rejects_skipped_phase() -> None:
    with pytest.raises(InvalidAgentTransitionError):
        transition_agent(new_run(), AgentState.ANALYZING, "skip phases")


def test_created_run_can_fail_with_reason() -> None:
    run = transition_agent(new_run(), AgentState.FAILED, "input invalid")
    assert run.state == AgentState.FAILED
    assert run.failure_reason == "input invalid"


def test_every_nonterminal_state_can_fail() -> None:
    run = new_run()
    for target in (
        AgentState.PLANNING,
        AgentState.COLLECTING,
        AgentState.ANALYZING,
        AgentState.VALIDATING,
        AgentState.RECOMMENDING,
    ):
        failed = transition_agent(run, AgentState.FAILED, "controlled failure")
        assert failed.state == AgentState.FAILED
        run = transition_agent(run, target, f"advance to {target}")
    failed = transition_agent(run, AgentState.FAILED, "controlled failure")
    assert failed.state == AgentState.FAILED


def test_completed_run_is_immutable_terminal_state() -> None:
    run = execute_nominal_workflow(new_run())
    with pytest.raises(TerminalAgentRunError):
        transition_agent(run, AgentState.FAILED, "too late")


def test_failed_run_is_immutable_terminal_state() -> None:
    run = transition_agent(new_run(), AgentState.FAILED, "controlled failure")
    with pytest.raises(TerminalAgentRunError):
        transition_agent(run, AgentState.PLANNING, "retry")


def test_transition_reason_cannot_be_blank() -> None:
    with pytest.raises(ValueError, match="reason is required"):
        transition_agent(new_run(), AgentState.PLANNING, "   ")


def test_agent_snapshot_round_trip_preserves_history() -> None:
    original = execute_nominal_workflow(new_run())
    restored = AgentRun.model_validate_json(original.model_dump_json())
    assert restored == original


def test_transition_map_has_expected_strict_edges() -> None:
    edge_count = sum(len(targets) for targets in ALLOWED_TRANSITIONS.values())
    assert len(AgentState) == 8
    assert edge_count == 12
