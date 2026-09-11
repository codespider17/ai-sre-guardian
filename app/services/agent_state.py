from datetime import UTC, datetime
from uuid import UUID

from app.schemas_agent import AgentRun, AgentState, AgentStep

TERMINAL_STATES = frozenset({AgentState.COMPLETED, AgentState.FAILED})

ALLOWED_TRANSITIONS: dict[AgentState, frozenset[AgentState]] = {
    AgentState.CREATED: frozenset({AgentState.PLANNING, AgentState.FAILED}),
    AgentState.PLANNING: frozenset({AgentState.COLLECTING, AgentState.FAILED}),
    AgentState.COLLECTING: frozenset({AgentState.ANALYZING, AgentState.FAILED}),
    AgentState.ANALYZING: frozenset({AgentState.VALIDATING, AgentState.FAILED}),
    AgentState.VALIDATING: frozenset({AgentState.RECOMMENDING, AgentState.FAILED}),
    AgentState.RECOMMENDING: frozenset({AgentState.COMPLETED, AgentState.FAILED}),
    AgentState.COMPLETED: frozenset(),
    AgentState.FAILED: frozenset(),
}


class InvalidAgentTransitionError(ValueError):
    pass


class TerminalAgentRunError(ValueError):
    pass


def create_agent_run(analysis_run_id: UUID) -> AgentRun:
    return AgentRun(analysis_run_id=analysis_run_id)


def transition_agent(
    run: AgentRun,
    target_state: AgentState,
    reason: str,
) -> AgentRun:
    if run.state in TERMINAL_STATES:
        raise TerminalAgentRunError(f"agent run is already terminal: {run.state}")
    if target_state not in ALLOWED_TRANSITIONS[run.state]:
        raise InvalidAgentTransitionError(
            f"transition is not allowed: {run.state} -> {target_state}"
        )
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise ValueError("transition reason is required")

    now = datetime.now(UTC)
    step = AgentStep(
        sequence=len(run.steps) + 1,
        from_state=run.state,
        to_state=target_state,
        reason=normalized_reason,
        occurred_at=now,
    )
    return run.model_copy(
        update={
            "state": target_state,
            "failure_reason": (
                normalized_reason
                if target_state == AgentState.FAILED
                else run.failure_reason
            ),
            "steps": [*run.steps, step],
            "updated_at": now,
        }
    )


def execute_nominal_workflow(run: AgentRun) -> AgentRun:
    workflow = (
        (AgentState.PLANNING, "analysis plan created"),
        (AgentState.COLLECTING, "evidence collection started"),
        (AgentState.ANALYZING, "evidence collection completed"),
        (AgentState.VALIDATING, "analysis result produced"),
        (AgentState.RECOMMENDING, "analysis result validated"),
        (AgentState.COMPLETED, "recommendation completed"),
    )
    current = run
    for target_state, reason in workflow:
        current = transition_agent(current, target_state, reason)
    return current
