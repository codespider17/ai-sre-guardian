from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, EvidenceItem
from app.schemas_ai import AIAnalysisOutcome


def persist_agent_ai_outcome(
    session: Session,
    *,
    analysis_run_id: UUID,
    agent_run_id: UUID,
    outcome: AIAnalysisOutcome,
) -> tuple[UUID, bool]:
    evidence_key = f"agent.{agent_run_id}.ai_analysis"
    existing = session.scalar(
        select(EvidenceItem).where(
            EvidenceItem.analysis_run_id == analysis_run_id,
            EvidenceItem.evidence_key == evidence_key,
        )
    )
    if existing is not None:
        return existing.id, False

    evidence = EvidenceItem(
        analysis_run_id=analysis_run_id,
        evidence_key=evidence_key,
        source_type="ai_analysis",
        source_ref=outcome.model or "rules_fallback",
        payload=outcome.model_dump(mode="json"),
    )
    session.add(evidence)
    session.flush()
    session.add(
        AuditEvent(
            entity_type="agent_run",
            entity_id=agent_run_id,
            action="agent.ai_analysis_recorded",
            actor="sre-agent",
            details={
                "analysis_run_id": str(analysis_run_id),
                "mode": str(outcome.mode),
                "model": outcome.model,
                "recommendation": str(outcome.analysis.recommendation),
                "confidence": outcome.analysis.confidence,
                "evidence_reference_count": len(outcome.analysis.evidence_refs),
            },
        )
    )
    return evidence.id, True
