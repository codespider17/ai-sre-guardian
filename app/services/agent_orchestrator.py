from uuid import UUID

from sqlalchemy.orm import Session

from app.models import AnalysisRun, AuditEvent, EvidenceItem
from app.schemas_agent import AgentRun, AgentState
from app.schemas_tools import ToolRequest
from app.services.agent_state import (
    TERMINAL_STATES,
    create_agent_run,
    transition_agent,
)
from app.services.read_only_tools import (
    CommandRunner,
    PrometheusReader,
    execute_read_only_tool,
    read_prometheus_query,
    run_read_only_command,
)

MAX_AGENT_TOOL_CALLS = 6


class AgentOrchestrationError(RuntimeError):
    def __init__(self, message: str, run: AgentRun) -> None:
        super().__init__(message)
        self.run = run


def _recommendation_for(analysis: AnalysisRun) -> str:
    if analysis.risk_level in {"high", "critical"}:
        return "manual_review_required"
    return "proceed_with_observation"


def orchestrate_agent_analysis(
    session: Session,
    analysis_run_id: UUID,
    requests: list[ToolRequest],
    command_runner: CommandRunner = run_read_only_command,
    prometheus_reader: PrometheusReader = read_prometheus_query,
) -> AgentRun:
    run = create_agent_run(analysis_run_id)
    current = run
    try:
        if not 1 <= len(requests) <= MAX_AGENT_TOOL_CALLS:
            raise ValueError("agent tool call count must be between 1 and 6")

        analysis = session.get(AnalysisRun, analysis_run_id)
        if analysis is None:
            raise ValueError("analysis run was not found")

        current = transition_agent(
            current,
            AgentState.PLANNING,
            "read-only tool plan created",
        )
        current = current.model_copy(
            update={"planned_tools": [str(request.tool) for request in requests]}
        )
        current = transition_agent(
            current,
            AgentState.COLLECTING,
            "authorized evidence collection started",
        )

        evidence_ids: list[UUID] = []
        for index, request in enumerate(requests, start=1):
            result = execute_read_only_tool(
                session,
                request,
                command_runner=command_runner,
                prometheus_reader=prometheus_reader,
            )
            evidence = EvidenceItem(
                analysis_run_id=analysis_run_id,
                evidence_key=(f"agent.{current.run_id}.{index}.{result.tool}"),
                source_type="agent_tool",
                source_ref=str(result.call_id),
                payload=result.model_dump(mode="json"),
            )
            session.add(evidence)
            session.flush()
            evidence_ids.append(evidence.id)
            session.add(
                AuditEvent(
                    entity_type="agent_run",
                    entity_id=current.run_id,
                    action="agent.tool_succeeded",
                    actor="sre-agent",
                    details={
                        "sequence": index,
                        "tool": str(result.tool),
                        "call_id": str(result.call_id),
                        "read_only": result.read_only,
                        "truncated": result.truncated,
                    },
                )
            )

        current = current.model_copy(update={"evidence_ids": evidence_ids})
        current = transition_agent(
            current,
            AgentState.ANALYZING,
            "authorized evidence collection completed",
        )
        current = current.model_copy(
            update={"recommendation": _recommendation_for(analysis)}
        )
        current = transition_agent(
            current,
            AgentState.VALIDATING,
            "deterministic recommendation produced",
        )
        current = transition_agent(
            current,
            AgentState.RECOMMENDING,
            "recommendation evidence references validated",
        )
        current = transition_agent(
            current,
            AgentState.COMPLETED,
            "read-only agent workflow completed",
        )
        session.add(
            AuditEvent(
                entity_type="agent_run",
                entity_id=current.run_id,
                action="agent.run_completed",
                actor="sre-agent",
                details={
                    "analysis_run_id": str(analysis_run_id),
                    "tool_count": len(requests),
                    "evidence_count": len(evidence_ids),
                    "recommendation": current.recommendation,
                },
            )
        )
        session.commit()
        return current
    except Exception as exc:
        session.rollback()
        failed = current
        if current.state not in TERMINAL_STATES:
            failed = transition_agent(
                current,
                AgentState.FAILED,
                "controlled agent orchestration failure",
            )
        session.add(
            AuditEvent(
                entity_type="agent_run",
                entity_id=failed.run_id,
                action="agent.run_failed",
                actor="sre-agent",
                details={
                    "analysis_run_id": str(analysis_run_id),
                    "error_type": type(exc).__name__,
                },
            )
        )
        session.commit()
        raise AgentOrchestrationError(
            "agent orchestration failed",
            failed,
        ) from exc
