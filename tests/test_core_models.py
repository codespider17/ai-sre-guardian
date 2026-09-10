import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models import (
    AnalysisRun,
    AuditEvent,
    ChangeEvent,
    EvidenceItem,
    Service,
)


def create_analysis_case(risk_score: int = 72) -> tuple[uuid.UUID, uuid.UUID]:
    suffix = uuid.uuid4().hex[:12]

    with SessionLocal() as session:
        service = Service(
            name=f"checkout-{suffix}",
            repository_full_name=f"codespider17/checkout-{suffix}",
            namespace="ai-sre-lab",
            workload_name="checkout-api",
        )
        session.add(service)
        session.flush()

        change = ChangeEvent(
            service_id=service.id,
            delivery_id=f"delivery-{suffix}",
            commit_sha=uuid.uuid4().hex + "12345678",
            git_ref="refs/heads/main",
            author="m1-integration-test",
            title="introduce reliability model",
            changed_files=["app/main.py", "deploy/helm/values.yaml"],
        )
        session.add(change)
        session.flush()

        analysis = AnalysisRun(
            change_event_id=change.id,
            status="completed",
            risk_score=risk_score,
            risk_level="high",
            summary="deterministic integration-test result",
        )
        session.add(analysis)
        session.flush()

        evidence = EvidenceItem(
            analysis_run_id=analysis.id,
            evidence_key="git.change.files",
            source_type="git",
            source_ref=change.commit_sha,
            payload={"changed_file_count": 2},
        )
        audit = AuditEvent(
            entity_type="analysis_run",
            entity_id=analysis.id,
            action="analysis.completed",
            actor="m1-integration-test",
            details={"risk_score": risk_score},
        )
        session.add_all([evidence, audit])
        session.commit()
        return service.id, analysis.id


def test_core_records_are_persisted() -> None:
    service_id, analysis_id = create_analysis_case()

    with SessionLocal() as session:
        service = session.get(Service, service_id)
        analysis = session.get(AnalysisRun, analysis_id)

        assert service is not None
        assert service.namespace == "ai-sre-lab"
        assert analysis is not None
        assert analysis.status == "completed"
        assert analysis.risk_score == 72
        assert analysis.risk_level == "high"


def test_database_rejects_invalid_risk_score() -> None:
    with pytest.raises(IntegrityError):
        create_analysis_case(risk_score=101)
