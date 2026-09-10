from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AnalysisRun, AuditEvent, ChangeEvent, EvidenceItem, Service
from app.schemas_change import ChangeEvaluationReceipt, ChangeEvaluationRequest
from app.schemas_risk import ChangeRiskInput
from app.services.change_risk import evaluate_change_risk


class ServiceNotRegisteredError(Exception):
    pass


def _build_receipt(
    session: Session,
    change_event: ChangeEvent,
    analysis_run: AnalysisRun,
    status: str,
) -> ChangeEvaluationReceipt:
    assert analysis_run.risk_score is not None
    assert analysis_run.risk_level is not None
    finding_count = session.scalar(
        select(func.count())
        .select_from(EvidenceItem)
        .where(EvidenceItem.analysis_run_id == analysis_run.id)
    )
    return ChangeEvaluationReceipt(
        delivery_id=change_event.delivery_id,
        status=status,
        change_event_id=change_event.id,
        analysis_run_id=analysis_run.id,
        risk_score=analysis_run.risk_score,
        risk_level=analysis_run.risk_level,
        finding_count=finding_count or 0,
    )


def evaluate_and_persist_change(
    session: Session,
    request: ChangeEvaluationRequest,
) -> ChangeEvaluationReceipt:
    existing_change = session.scalar(
        select(ChangeEvent).where(ChangeEvent.delivery_id == request.delivery_id)
    )
    if existing_change is not None:
        existing_analysis = session.scalar(
            select(AnalysisRun).where(AnalysisRun.change_event_id == existing_change.id)
        )
        if existing_analysis is None:
            raise RuntimeError("existing change event has no analysis run")
        return _build_receipt(
            session,
            existing_change,
            existing_analysis,
            "duplicate",
        )

    service = session.scalar(
        select(Service).where(
            Service.repository_full_name == request.repository_full_name
        )
    )
    if service is None:
        raise ServiceNotRegisteredError(request.repository_full_name)

    change_event = ChangeEvent(
        service_id=service.id,
        delivery_id=request.delivery_id,
        commit_sha=request.commit_sha,
        git_ref=request.git_ref,
        author=request.author,
        title=request.title,
        changed_files=request.changed_files,
    )
    session.add(change_event)
    session.flush()

    risk = evaluate_change_risk(
        ChangeRiskInput(
            repository_full_name=request.repository_full_name,
            commit_sha=request.commit_sha,
            changed_files=request.changed_files,
        )
    )
    now = datetime.now(UTC)
    analysis_run = AnalysisRun(
        change_event_id=change_event.id,
        status="completed",
        risk_score=risk.score,
        risk_level=risk.level,
        summary=(f"deterministic risk evaluation matched {len(risk.findings)} rules"),
        finished_at=now,
    )
    session.add(analysis_run)
    session.flush()

    for finding in risk.findings:
        session.add(
            EvidenceItem(
                analysis_run_id=analysis_run.id,
                evidence_key=f"risk.rule.{finding.rule_id}",
                source_type="deterministic_rule",
                source_ref=request.commit_sha,
                payload={
                    "rule_id": finding.rule_id,
                    "score": finding.score,
                    "title": finding.title,
                    "explanation": finding.explanation,
                    "evidence_files": finding.evidence_files,
                },
            )
        )

    session.add(
        AuditEvent(
            entity_type="analysis_run",
            entity_id=analysis_run.id,
            action="change.risk_evaluated",
            actor="risk-engine",
            details={
                "delivery_id": request.delivery_id,
                "risk_score": risk.score,
                "risk_level": risk.level,
                "finding_count": len(risk.findings),
            },
        )
    )
    session.commit()
    session.refresh(change_event)
    session.refresh(analysis_run)
    return _build_receipt(session, change_event, analysis_run, "evaluated")
