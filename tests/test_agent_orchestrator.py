import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import AnalysisRun, AuditEvent, ChangeEvent, EvidenceItem, Service
from app.schemas_agent import AgentState
from app.schemas_ai import AIAnalysisOutcome, StructuredAIAnalysis
from app.schemas_tools import (
    KubernetesResourceKind,
    PrometheusQueryId,
    ToolName,
    ToolRequest,
)
from app.services.agent_orchestrator import (
    AgentOrchestrationError,
    orchestrate_agent_analysis,
)


def create_analysis(risk_level: str = "critical") -> UUID:
    suffix = uuid4().hex
    with SessionLocal() as session:
        service = Service(
            name=f"agent-{suffix}",
            repository_full_name=f"codespider17/agent-{suffix}",
            namespace="ai-sre-system",
            workload_name="ai-sre-guardian",
        )
        session.add(service)
        session.flush()
        change = ChangeEvent(
            service_id=service.id,
            delivery_id=f"agent-{suffix}",
            commit_sha="d" * 40,
            git_ref="refs/heads/main",
            author="agent-test",
            title="agent orchestration test",
            changed_files=["app/main.py"],
        )
        session.add(change)
        session.flush()
        analysis = AnalysisRun(
            change_event_id=change.id,
            status="completed",
            risk_score=90 if risk_level == "critical" else 10,
            risk_level=risk_level,
            summary="fixture",
            finished_at=datetime.now(UTC),
        )
        session.add(analysis)
        session.commit()
        return analysis.id


def tool_requests(analysis_id: UUID) -> list[ToolRequest]:
    return [
        ToolRequest(
            tool=ToolName.KUBERNETES_WORKLOAD,
            namespace="ai-sre-system",
            resource_kind=KubernetesResourceKind.DEPLOYMENT,
            resource_name="ai-sre-guardian",
        ),
        ToolRequest(
            tool=ToolName.KUBERNETES_EVENTS,
            namespace="ai-sre-system",
            resource_kind=KubernetesResourceKind.POD,
            resource_name="ai-sre-guardian-test",
            limit=10,
        ),
        ToolRequest(
            tool=ToolName.KUBERNETES_LOGS,
            namespace="ai-sre-system",
            resource_kind=KubernetesResourceKind.POD,
            resource_name="ai-sre-guardian-test",
            limit=20,
        ),
        ToolRequest(
            tool=ToolName.PROMETHEUS_QUERY,
            namespace="ai-sre-system",
            service_name="ai-sre-guardian",
            query_id=PrometheusQueryId.WORKLOAD_AVAILABILITY,
        ),
        ToolRequest(tool=ToolName.CHANGE_RISK, analysis_run_id=analysis_id),
        ToolRequest(
            tool=ToolName.ANALYSIS_EVIDENCE,
            analysis_run_id=analysis_id,
            limit=20,
        ),
    ]


def command_runner(arguments: list[str]) -> str:
    if "events" in arguments:
        return json.dumps({"items": [{"reason": "Started"}]})
    if "logs" in arguments:
        return "application ready\n"
    return json.dumps({"kind": "Deployment", "metadata": {"name": "ai-sre-guardian"}})


def prometheus_reader(query: str) -> dict[str, object]:
    assert "ai-sre-system" in query
    return {"status": "success", "data": {"result": []}}


def run_agent(analysis_id: UUID):
    with SessionLocal() as session:
        return orchestrate_agent_analysis(
            session,
            analysis_id,
            tool_requests(analysis_id),
            command_runner=command_runner,
            prometheus_reader=prometheus_reader,
        )


def test_nominal_agent_orchestration_completes_six_tools() -> None:
    run = run_agent(create_analysis())
    assert run.state == AgentState.COMPLETED
    assert len(run.planned_tools) == 6
    assert len(run.evidence_ids) == 6


def test_nominal_agent_persists_six_evidence_and_seven_audits() -> None:
    run = run_agent(create_analysis())
    with SessionLocal() as session:
        evidence_count = session.scalar(
            select(func.count())
            .select_from(EvidenceItem)
            .where(EvidenceItem.id.in_(run.evidence_ids))
        )
        audit_count = session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.entity_id == run.run_id)
        )
    assert evidence_count == 6
    assert audit_count == 7


def test_critical_risk_requires_manual_review() -> None:
    run = run_agent(create_analysis("critical"))
    assert run.recommendation == "manual_review_required"


def test_low_risk_can_proceed_with_observation() -> None:
    run = run_agent(create_analysis("low"))
    assert run.recommendation == "proceed_with_observation"


def test_agent_state_history_remains_strictly_ordered() -> None:
    run = run_agent(create_analysis())
    assert [step.sequence for step in run.steps] == list(range(1, 7))
    assert [step.to_state for step in run.steps] == [
        AgentState.PLANNING,
        AgentState.COLLECTING,
        AgentState.ANALYZING,
        AgentState.VALIDATING,
        AgentState.RECOMMENDING,
        AgentState.COMPLETED,
    ]


def test_tool_evidence_records_read_only_execution() -> None:
    run = run_agent(create_analysis())
    with SessionLocal() as session:
        evidence = session.get(EvidenceItem, run.evidence_ids[0])
    assert evidence is not None
    assert evidence.source_type == "agent_tool"
    assert evidence.payload["read_only"] is True
    assert evidence.payload["status"] == "succeeded"


def test_denied_tool_fails_agent_and_persists_sanitized_audit() -> None:
    analysis_id = create_analysis()
    request = ToolRequest(
        tool=ToolName.KUBERNETES_WORKLOAD,
        namespace="kube-system",
        resource_kind=KubernetesResourceKind.DEPLOYMENT,
        resource_name="coredns",
    )
    with SessionLocal() as session, pytest.raises(AgentOrchestrationError) as captured:
        orchestrate_agent_analysis(
            session,
            analysis_id,
            [request],
            command_runner=command_runner,
            prometheus_reader=prometheus_reader,
        )
    assert captured.value.run.state == AgentState.FAILED
    with SessionLocal() as session:
        audits = session.scalars(
            select(AuditEvent).where(AuditEvent.entity_id == captured.value.run.run_id)
        ).all()
    assert len(audits) == 1
    assert audits[0].action == "agent.run_failed"
    assert audits[0].details["error_type"] == "ToolAccessDeniedError"


def test_deepseek_outcome_is_persisted_and_drives_recommendation() -> None:
    analysis_id = create_analysis("critical")
    outcome = AIAnalysisOutcome(
        mode="deepseek",
        model="deepseek-v4-flash",
        analysis=StructuredAIAnalysis(
            risk_level="critical",
            summary="Evidence-backed critical change risk.",
            recommendation="block",
            confidence=0.95,
            evidence_refs=["evidence:fixture"],
            reasoning_points=["critical deterministic evidence"],
        ),
    )

    with SessionLocal() as session:
        run = orchestrate_agent_analysis(
            session,
            analysis_id,
            [
                ToolRequest(
                    tool=ToolName.CHANGE_RISK,
                    analysis_run_id=analysis_id,
                )
            ],
            ai_outcome=outcome,
        )

    assert run.state == AgentState.COMPLETED
    assert run.recommendation == "block"
    assert len(run.evidence_ids) == 2

    with SessionLocal() as session:
        ai_evidence = session.scalar(
            select(EvidenceItem).where(
                EvidenceItem.analysis_run_id == analysis_id,
                EvidenceItem.evidence_key == f"agent.{run.run_id}.ai_analysis",
            )
        )
        assert ai_evidence is not None
        assert ai_evidence.source_type == "ai_analysis"
        assert ai_evidence.source_ref == "deepseek-v4-flash"
        assert ai_evidence.payload["mode"] == "deepseek"
        assert ai_evidence.payload["analysis"]["recommendation"] == "block"

        ai_audits = list(
            session.scalars(
                select(AuditEvent).where(
                    AuditEvent.entity_type == "agent_run",
                    AuditEvent.entity_id == run.run_id,
                    AuditEvent.action == "agent.ai_analysis_recorded",
                )
            )
        )
        assert len(ai_audits) == 1
        assert ai_audits[0].details["mode"] == "deepseek"
        assert ai_audits[0].details["recommendation"] == "block"
